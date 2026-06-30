import random
from game_state import session

def clean_dead_casters():
    alive_ids = {p for p, data in session.players.items() if data["is_alive"]}
    
    # Очищаем только те баффы, которые хранятся как словари (с привязкой к ID кастера)
    for cat in ["atk", "def", "vamp"]:
        buff_dict = session.party_buffs[cat]
        for cid in list(buff_dict.keys()):
            if cid not in alive_ids: 
                del buff_dict[cid]
                
    for cat in ["def_down", "atk_down"]:
        debuff_dict = session.boss_debuffs[cat]
        for cid in list(debuff_dict.keys()):
            if cid not in alive_ids: 
                del debuff_dict[cid]
                
    # Доты очищаем по сохраненному caster_id
    session.boss_debuffs["dots"] = [d for d in session.boss_debuffs["dots"] if d.get("caster_id") in alive_ids]

def execute_skill(p_id, player, skill, target_id):
    sid = skill["id"]
    action_text = f"\nИспользует **{skill['name']}**"
    is_ode = False
    
    base_dmg = 0
    if sid == "warrior_execute": base_dmg = random.randint(79, 80) if session.boss_hp < session.boss_max_hp/2 else random.randint(39, 40)
    elif sid in ["mage_fireball", "mage_ice"]: base_dmg = random.randint(29, 45)
    elif sid == "mage_lightning": base_dmg = random.randint(45, 60)
    elif sid in ["bard_solo", "priest_smite"]: base_dmg = random.randint(15, 25)
    elif sid == "ranger_shot": base_dmg = random.randint(45, 65)
    elif sid == "necro_touch": base_dmg = random.randint(15, 35)

    dmg = 0
    if base_dmg > 0:
        atk_mod = 1.0 + sum(b["value"] for b in session.party_buffs["atk"].values()) - sum(d.get("value", 0.3) for d in player["debuffs"] if d["type"]=="ослабление")
        boss_def = session.boss_base_def - sum(b["value"] for b in session.boss_debuffs["def_down"].values())
        dmg = max(1, int((base_dmg * max(0.1, atk_mod)) * (1.0 - boss_def)))
        action_text += f" и наносит **{dmg}** урона!"
        
    if sid == "warrior_shield": session.party_buffs["def"]["warrior_shield"] = {"value": 0.25, "duration": 7}; action_text += " 🛡️ Защита усилена!"
    elif sid == "warrior_provoke":
        session.boss_debuffs["def_down"]["warrior_provoke"] = {"value": 0.20, "duration": 7}; action_text += " 📢 Босс спровоцирован!"
        if random.random() < 0.3:
            c_dmg = max(1, int(random.randint(40,65) * (1.0 - sum(b["value"] for b in session.party_buffs["def"].values()))))
            player["hp"] = max(0, player["hp"] - c_dmg); action_text += f"\n⚠️ Босс отвечает вне очереди! Получено **{c_dmg}** урона!"
            if player["hp"] <= 0: player["is_alive"] = False
    elif sid == "mage_fireball" and random.random() < 0.9: session.boss_debuffs["dots"].append({"type": "горение", "damage": 9, "duration": 3, "caster_id": p_id}); action_text += " 🔥 Босс подожжен!"
    elif sid == "mage_ice" and random.random() < 0.9:
        if session.boss_slow_stacks >= 2: action_text += " ❌ У босса иммунитет ко льду!"
        else: session.boss_slow_stacks += 1; session.boss_cooldown_counter = max(0, session.boss_cooldown_counter - 1); action_text += " ❄️ Зарядка заморожена!"
    elif sid == "mage_lightning" and random.random() < 0.3: player["hp"] = max(1, player["hp"] - 30); action_text += "\n⚠️ Маг теряет 30 HP от перегрузки!"
    elif sid == "bard_regen": session.party_buffs["regen"].append({"duration": 4}); session.party_buffs["atk"]["bard_regen"] = {"value": 0.10, "duration": 4}; action_text += " 🎺 Атака и реген отряда!"
    elif sid == "bard_ode":
        if target_id:
            session.party_buffs["atk"]["bard_ode"] = {"value": 0.20, "duration": 4}
            if target_id in session.turn_order: session.turn_order.remove(target_id)
            session.turn_order.insert(1, target_id)
            action_text += " 🎸 Выбранный союзник получает ход вне очереди!"
            is_ode = True
        else:
            action_text += " 🎸 Но слушать оказалось некому!"
    elif sid == "priest_smite":
        for p in session.players.values():
            if p["is_alive"]: p["hp"] = min(100, p["hp"] + random.randint(7,12))
    elif sid == "priest_great_heal" and target_id: session.players[target_id]["hp"] = min(100, session.players[target_id]["hp"] + random.randint(70,90))
    elif sid == "priest_heal":
        for p in session.players.values():
            if p["is_alive"]: p["hp"] = min(100, p["hp"] + random.randint(30,45))
    elif sid == "ranger_strafe": player["strafe_turns"] = 4; action_text += " 🌪️ Стойка стрейфа активирована!"
    elif sid == "ranger_focus": session.boss_debuffs["def_down"]["ranger_focus"] = {"value": 0.40, "duration": 6}; action_text += " 🎯 Защита босса снижена на 40%!"
    elif sid == "necro_vampire": session.party_buffs["vamp"]["necro_vampire"] = {"duration": 7}; action_text += " 🦇 Наложен Вампиризм!"
    elif sid == "necro_curse": session.boss_debuffs["atk_down"]["necro_curse"] = {"value": 0.30, "duration": 4}; action_text += " 💀 Атака босса снижена на 30%!"

    session.boss_hp = max(0, session.boss_hp - dmg)
    if session.party_buffs["vamp"] and dmg > 0:
        v_heal = int(dmg * 0.5); player["hp"] = min(100, player["hp"] + v_heal); action_text += f" 🦇 Отхил вампиризмом: {v_heal} HP!"
        
    return action_text, dmg, is_ode

def process_global_tick(p_id):
    tick_text = ""
    for cat in ["atk", "def", "vamp"]:
        for sid_key in list(session.party_buffs[cat].keys()):
            session.party_buffs[cat][sid_key]["duration"] -= 1
            if session.party_buffs[cat][sid_key]["duration"] <= 0: del session.party_buffs[cat][sid_key]
            
    for cat in ["def_down", "atk_down"]:
        for sid_key in list(session.boss_debuffs[cat].keys()):
            session.boss_debuffs[cat][sid_key]["duration"] -= 1
            if session.boss_debuffs[cat][sid_key]["duration"] <= 0: del session.boss_debuffs[cat][sid_key]

    regen_heal = len(session.party_buffs["regen"]) * 7
    if regen_heal > 0:
        for p in session.players.values():
            if p["is_alive"]: p["hp"] = min(100, p["hp"] + regen_heal)
        tick_text += f"\n💚 Реген: отряд восстановил {regen_heal} HP."
    for r in session.party_buffs["regen"]: r["duration"] -= 1
    session.party_buffs["regen"] = [r for r in session.party_buffs["regen"] if r["duration"] > 0]
    
    dot_dmg = sum(d["damage"] for d in session.boss_debuffs["dots"])
    if dot_dmg > 0:
        session.boss_hp = max(0, session.boss_hp - dot_dmg)
        tick_text += f"\n🔥 Босс получает {dot_dmg} период. урона."
    for d in session.boss_debuffs["dots"]: d["duration"] -= 1
    session.boss_debuffs["dots"] = [d for d in session.boss_debuffs["dots"] if d["duration"] > 0]
    
    for p in session.players.values():
        if not p["is_alive"]: continue
        p_dot = sum(9 for d in p["debuffs"] if d["type"] in ["горение", "отравление"])
        if p_dot > 0:
            p["hp"] -= p_dot
            tick_text += f"\n☠️ {p['name']} получает {p_dot} урон от дебаффов."
            if p["hp"] <= 0:
                p["is_alive"] = False
                tick_text += f" 💀 Погиб!"
                if p["id"] in session.turn_order and p["id"] != p_id: session.turn_order.remove(p["id"])
        for d in p["debuffs"]: d["duration"] -= 1
        p["debuffs"] = [d for d in p["debuffs"] if d["duration"] > 0]
        
    for p in session.players.values():
        if p["is_alive"] and p.get("strafe_turns", 0) > 0:
            boss_def = session.boss_base_def - sum(b["value"] for b in session.boss_debuffs["def_down"].values())
            dmg1 = max(1, int(random.randint(10,15) * (1.0 - boss_def)))
            dmg2 = max(1, int(random.randint(10,15) * (1.0 - boss_def)))
            session.boss_hp = max(0, session.boss_hp - (dmg1 + dmg2))
            tick_text += f"\n🏹 Авто-Стрейф ({p['name']}) наносит {dmg1} и {dmg2} урона!"
            p["strafe_turns"] -= 1
            
    alive_count = len([p for p in session.players.values() if p["is_alive"]])
    max_cd = 3 if alive_count >= 5 else 2 if alive_count >= 3 else 1
    session.boss_cooldown_counter += 1
    boss_trigger = False
    if session.boss_cooldown_counter >= max_cd:
        boss_trigger = True
        session.boss_cooldown_counter = 0
        
    return tick_text, boss_trigger

def execute_boss_attack(alive_players):
    if session.boss_turns_taken >= 3 and session.boss_ultimate:
        boss_atk = session.boss_ultimate
        session.boss_turns_taken = 0
        is_ultimate = True
    else:
        boss_atk = random.choice(session.boss_attacks)
        session.boss_turns_taken += 1
        is_ultimate = False

    targets = []
    if boss_atk["target"] == "aoe":
        targets = alive_players
        atk_type_text = "масштабную AOE атаку"
    elif boss_atk["target"].startswith("multi_"):
        count = int(boss_atk["target"].split("_")[1])
        targets = random.sample(alive_players, min(count, len(alive_players)))
        atk_type_text = f"атаку по {len(targets)} целям"
    else:
        targets = [random.choice(alive_players)]
        atk_type_text = "точечную атаку"

    if is_ultimate:
        boss_atk_text = f"🌟 **УЛЬТИМЕЙТ!** 👹 **{session.boss_name}** обрушивает {atk_type_text} **{boss_atk['name']}**!"
    else:
        boss_atk_text = f"👹 **{session.boss_name}** проводит {atk_type_text} **{boss_atk['name']}**!"
    
    death_reports = ""
    total_heal = 0
    for t in targets:
        atk_mod = 1.0 - sum(b["value"] for b in session.boss_debuffs["atk_down"].values())
        base_dmg = int(random.randint(boss_atk["min_damage"], boss_atk["max_damage"]) * max(0.1, atk_mod))
        def_mod = 1.0 - sum(b["value"] for b in session.party_buffs["def"].values())
        boss_damage = max(1, int(base_dmg * def_mod))
        
        t["hp"] = max(0, t["hp"] - boss_damage)
        boss_atk_text += f"\n💥 <@{t['id']}> получает **{boss_damage}** урона."

        if boss_atk.get("heal_pct") and boss_damage > 0:
            total_heal += int(boss_damage * boss_atk["heal_pct"])
        
        if boss_atk.get("effect") and t["hp"] > 0:
            t["debuffs"].append({"type": boss_atk["effect"]["type"], "duration": boss_atk["effect"]["duration"], "value": boss_atk["effect"].get("value", 0.30)})
            boss_atk_text += f" ☣️ Наложен эффект: {boss_atk['effect']['type']}!"

        if t["hp"] <= 0:
            t["is_alive"] = False; death_reports += f"\n💀 <@{t['id']}> погиб!"
            if t["id"] in session.turn_order: session.turn_order.remove(t["id"])

    if total_heal > 0:
        session.boss_hp = min(session.boss_max_hp, session.boss_hp + total_heal)
        boss_atk_text += f"\n🩸 Босс восстанавливает себе **{total_heal}** HP!"
        
    return boss_atk_text, death_reports