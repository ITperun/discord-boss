import random
import database
from game_state import session

def clean_dead_casters():
    alive_ids = {p for p, data in session.players.items() if data["is_alive"]}
    for cat in ["atk", "def", "vamp"]:
        buff_dict = session.party_buffs[cat]
        for cid in list(buff_dict.keys()):
            if cid not in alive_ids: del buff_dict[cid]
    for cat in ["def_down", "atk_down"]:
        debuff_dict = session.boss_debuffs[cat]
        for cid in list(debuff_dict.keys()):
            if cid not in alive_ids: del debuff_dict[cid]
    session.boss_debuffs["dots"] = [d for d in session.boss_debuffs["dots"] if d.get("caster_id") in alive_ids]

def get_combat_stats(p_id, player):
    stats = database.get_total_stats(p_id)
    weakness = sum(d.get("value", 0.3) for d in player["debuffs"] if d["type"] == "ослабление")
    
    if weakness > 0:
        stat_mod = max(0.1, 1.0 - weakness)
        stats["STR"] = max(1, int(stats["STR"] * stat_mod))
        stats["AGI"] = max(1, int(stats["AGI"] * stat_mod))
        stats["INT"] = max(1, int(stats["INT"] * stat_mod))
        stats["CHA"] = max(1, int(stats["CHA"] * stat_mod))
        
    return stats

def execute_skill(p_id, player, skill, target_id):
    sid = skill["id"]
    action_text = f"\nИспользует **{skill['name']}**"
    is_ode = False
    
    stats = get_combat_stats(p_id, player)
    
    base_dmg = 0
    if sid == "warrior_execute": 
        if session.boss_hp < (session.boss_max_hp / 2):
            base_dmg = 40 + int(stats["STR"] * 4.0) 
            action_text += " 🩸 **ДОБИВАНИЕ!**"
        else:
            base_dmg = 20 + int(stats["STR"] * 2.0)
            
    elif sid in ["mage_fireball", "mage_ice"]: base_dmg = 15 + int(stats["INT"] * 1.5)
    elif sid == "mage_lightning": base_dmg = 25 + int(stats["INT"] * 2.0)
    elif sid == "priest_smite": base_dmg = 10 + int(stats["INT"] * 1.0)
    elif sid == "bard_solo": base_dmg = 10 + int(stats["INT"] * 1.0)
    elif sid == "ranger_shot": base_dmg = 25 + int(stats["AGI"] * 1.8)
    elif sid == "necro_touch": base_dmg = 10 + int(stats["INT"] * 1.2)

    is_crit = False
    if base_dmg > 0 and random.randint(1, 100) <= stats["LUK"]:
        base_dmg = int(base_dmg * 1.5)
        is_crit = True

    dmg = 0
    if base_dmg > 0:
        # ПРОВЕРКА НА ПОЛЕТ ДРАКОНА
        if session.dragon_in_flight and skill.get("type") == "melee":
            action_text += f"... Но Дракон слишком высоко! 🦅 Атака рассекает лишь воздух (0 урона)."
            # Пропускаем расчет урона, оставляем dmg = 0
        else:
            if session.dragon_in_flight and skill.get("element") == "ice":
                base_dmg *= 2
                action_text += " ❄️ Лед наносит ДВОЙНОЙ урон по летящей цели!"

            atk_mod = 1.0 + sum(b["value"] for b in session.party_buffs["atk"].values())
            atk_mod = max(0.1, atk_mod) 
            
            # Расколотая чешуя обнуляет базовую защиту босса
            boss_def = 0.0 if session.boss_debuffs.get("shattered_scales", 0) > 0 else session.boss_base_def
            boss_def -= sum(b["value"] for b in session.boss_debuffs["def_down"].values())
            
            dmg = max(1, int((base_dmg * atk_mod) * (1.0 - boss_def)))
            action_text += f" и наносит **{dmg}** урона!"
            if is_crit: action_text += " 💥 **КРИТИЧЕСКИЙ УДАР!**"
        
    if sid == "warrior_shield": session.party_buffs["def"][p_id] = {"value": 0.35, "duration": 10}; action_text += " 🛡️ Защита усилена!"
    elif sid == "warrior_provoke":
        session.boss_debuffs["def_down"][p_id] = {"value": 0.30, "duration": 10}; action_text += " 📢 Босс спровоцирован!"
        if random.random() < 0.3 and not session.dragon_in_flight: # В полете босс не отвечает на провокацию
            def_mod = 1.0
            for b in session.party_buffs["def"].values(): def_mod *= (1.0 - b["value"])
            c_dmg = max(1, int(random.randint(40,65) * def_mod))
            player["hp"] = max(0, player["hp"] - c_dmg); action_text += f"\n⚠️ Босс отвечает! Получено **{c_dmg}** урона!"
            if player["hp"] <= 0: 
                player["is_alive"] = False
                if session.boss_name == "Проклятый Некромант": player["is_skeleton"] = True
                if not player.get("is_skeleton") and player["id"] in session.turn_order:
                    session.turn_order.remove(player["id"])
            
    elif sid == "mage_fireball" and random.random() < 0.9: session.boss_debuffs["dots"].append({"type": "горение", "damage": 12, "duration": 5, "caster_id": p_id}); action_text += " 🔥 Босс подожжен!"
    elif sid == "mage_ice" and random.random() < 0.9:
        if session.dragon_in_flight:
            action_text += " ❌ В полёте дракон иммунен к заморозке счетчика!"
        elif session.boss_slow_stacks >= 2: 
            action_text += " ❌ У босса иммунитет ко льду!"
        else: 
            session.boss_slow_stacks += 1
            session.boss_cooldown_counter = 0
            action_text += " ❄️ Подготовка атаки босса ПОЛНОСТЬЮ СБИТА!"
    elif sid == "mage_lightning" and random.random() < 0.3: player["hp"] = max(1, player["hp"] - 30); action_text += "\n⚠️ Маг теряет 30 HP от перегрузки!"
    
    elif sid == "bard_regen": 
        cha_bonus = (stats["CHA"] * 0.005)
        session.party_buffs["regen"].append({"duration": 10})
        session.party_buffs["atk"][p_id] = {"value": 0.10 + cha_bonus, "duration": 10}
        action_text += f" 🎺 Атака (+{int((0.10+cha_bonus)*100)}%) и реген отряда!"
    elif sid == "bard_ode":
        if target_id:
            cha_bonus = (stats["CHA"] * 0.005)
            session.party_buffs["atk"][p_id] = {"value": 0.20 + cha_bonus, "duration": 5}
            if target_id in session.turn_order: session.turn_order.remove(target_id)
            session.turn_order.insert(1, target_id)
            action_text += " 🎸 Выбранный союзник получает ход вне очереди!"
            is_ode = True
        else:
            action_text += " 🎸 Но слушать оказалось некому!"
            
    elif sid == "priest_smite":
        heal_amt = 8 + int(stats["INT"] * 0.5)
        for p in session.players.values():
            if p["is_alive"]: p["hp"] = min(p["max_hp"], p["hp"] + heal_amt)
        action_text += f" ✨ Отряд исцелен на **{heal_amt}** HP!"
    elif sid == "priest_great_heal" and target_id: 
        heal_amt = 40 + int(stats["INT"] * 2.0)
        target = session.players[target_id]
        actual_heal = min(target["max_hp"] - target["hp"], heal_amt)
        target["hp"] += actual_heal
        mention = target['name'] if target.get('is_npc') else f"<@{target_id}>"
        action_text += f" 💖 На {mention} восстановлено **{actual_heal}** HP!"
    elif sid == "priest_heal":
        heal_amt = 15 + int(stats["INT"] * 1.5)
        for p in session.players.values():
            if p["is_alive"]: p["hp"] = min(p["max_hp"], p["hp"] + heal_amt)
        action_text += f" 🌊 Каждый член отряда восстанавливает **{heal_amt}** HP!"
            
    elif sid == "ranger_strafe": player["strafe_turns"] = 5; action_text += " 🌪️ Стойка стрейфа активирована!"
    elif sid == "ranger_focus": session.boss_debuffs["def_down"][p_id] = {"value": 0.40, "duration": 7}; action_text += " 🎯 Защита босса снижена на 40%!"
    
    elif sid == "necro_vampire": session.party_buffs["vamp"][p_id] = {"duration": 12}; action_text += " 🦇 Наложен Вампиризм!"
    elif sid == "necro_curse": session.boss_debuffs["atk_down"][p_id] = {"value": 0.35, "duration": 10}; action_text += " 💀 Атака босса снижена на 35%!"

    session.boss_hp = max(0, session.boss_hp - dmg)
    
    # ЛОГИКА ДПС-ЧЕКА В ПОЛЕТЕ
    if session.dragon_in_flight and dmg > 0:
        session.dragon_flight_damage += dmg
        action_text += f"\n🎯 **Урон по крыльям: {session.dragon_flight_damage}/{session.dragon_flight_threshold} HP!**"
        
        if session.dragon_flight_damage >= session.dragon_flight_threshold:
            session.dragon_in_flight = False
            fall_dmg = 500
            session.boss_hp = max(0, session.boss_hp - fall_dmg)
            session.boss_debuffs["shattered_scales"] = 3
            action_text += f"\n💥 **КРЫЛЬЯ ПРОБИТЫ!** Дракон с грохотом рушится на землю, получая **{fall_dmg}** урона от падения! Его чешуя расколота (защита 0% на 3 хода)!"

    if session.party_buffs["vamp"] and dmg > 0:
        v_heal = int(dmg * 0.6); player["hp"] = min(player["max_hp"], player["hp"] + v_heal); action_text += f" 🦇 Отхил: **{v_heal}** HP!"
        
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

    if session.boss_debuffs.get("shattered_scales", 0) > 0:
        session.boss_debuffs["shattered_scales"] -= 1

    regen_heal = len(session.party_buffs["regen"]) * 10
    if regen_heal > 0:
        for p in session.players.values():
            if p["is_alive"]: p["hp"] = min(p["max_hp"], p["hp"] + regen_heal)
        tick_text += f"\n💚 Реген: отряд восстановил **{regen_heal}** HP."
    for r in session.party_buffs["regen"]: r["duration"] -= 1
    session.party_buffs["regen"] = [r for r in session.party_buffs["regen"] if r["duration"] > 0]
    
    dot_dmg = sum(d["damage"] for d in session.boss_debuffs["dots"])
    if dot_dmg > 0:
        session.boss_hp = max(0, session.boss_hp - dot_dmg)
        tick_text += f"\n🔥 Босс получает **{dot_dmg}** период. урона."
    for d in session.boss_debuffs["dots"]: d["duration"] -= 1
    session.boss_debuffs["dots"] = [d for d in session.boss_debuffs["dots"] if d["duration"] > 0]
    
    for p in session.players.values():
        if not p["is_alive"]: continue
        p_dot = sum(9 for d in p["debuffs"] if d["type"] in ["горение", "отравление"])
        if p_dot > 0:
            p["hp"] -= p_dot
            tick_text += f"\n☠️ {p['name']} получает **{p_dot}** урон от дебаффов."
            if p["hp"] <= 0:
                p["is_alive"] = False
                if session.boss_name == "Проклятый Некромант": p["is_skeleton"] = True
                tick_text += f" 💀 Погиб!"
                if not p.get("is_skeleton") and p["id"] in session.turn_order and p["id"] != p_id: 
                    session.turn_order.remove(p["id"])
        for d in p["debuffs"]: d["duration"] -= 1
        p["debuffs"] = [d for d in p["debuffs"] if d["duration"] > 0]
        
    for p in session.players.values():
        if p["is_alive"] and p.get("strafe_turns", 0) > 0:
            stats = get_combat_stats(p["id"], p)
            
            boss_def = 0.0 if session.boss_debuffs.get("shattered_scales", 0) > 0 else session.boss_base_def
            boss_def -= sum(b["value"] for b in session.boss_debuffs["def_down"].values())
            boss_def = max(0.0, boss_def)
            
            base_arr = 5 + int(stats["AGI"] * 0.5)
            dmg1 = max(1, int(random.randint(base_arr, base_arr+5) * (1.0 - boss_def)))
            dmg2 = max(1, int(random.randint(base_arr, base_arr+5) * (1.0 - boss_def)))
            total_dmg = dmg1 + dmg2
            
            session.boss_hp = max(0, session.boss_hp - total_dmg)
            tick_text += f"\n🏹 Авто-Стрейф ({p['name']}) наносит **{dmg1}** и **{dmg2}** урона!"
            
            if session.dragon_in_flight:
                session.dragon_flight_damage += total_dmg
                tick_text += f" 🎯 (Урон по крыльям: {session.dragon_flight_damage}/{session.dragon_flight_threshold})"
                if session.dragon_flight_damage >= session.dragon_flight_threshold:
                    session.dragon_in_flight = False
                    fall_dmg = 200
                    session.boss_hp = max(0, session.boss_hp - fall_dmg)
                    session.boss_debuffs["shattered_scales"] = 3
                    tick_text += f"\n💥 **КРЫЛЬЯ ПРОБИТЫ!** Дракон рушится на землю, получая **{fall_dmg}** урона! Чешуя расколота!"

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
    skeletons = [p for p in session.players.values() if not p["is_alive"] and p.get("is_skeleton")]

    is_ultimate = False
    boss_atk = None

    # 1. Если Дракон в полете - он не атакует, а считает ходы до Армагеддона
    if session.dragon_in_flight:
        session.dragon_flight_timer -= 1
        if session.dragon_flight_timer <= 0:
            session.dragon_in_flight = False
            boss_atk = session.boss_ultimate
            is_ultimate = True
            # Начинается Армагеддон!
        else:
            return f"🦅 **Дракон парит высоко в небе!** Он накапливает энергию для сокрушительного удара... (Осталось до Армагеддона: {session.dragon_flight_timer} хода босса)", ""

    # 2. Проверка на активацию Взлета или обычного Ультимейта
    elif session.boss_turns_taken >= 3 and session.boss_ultimate:
        if session.boss_ultimate.get("is_flight"):
            session.dragon_in_flight = True
            session.dragon_flight_timer = session.boss_ultimate.get("flight_turns", 3)
            session.dragon_flight_damage = 0
            session.dragon_flight_threshold = session.boss_ultimate.get("flight_threshold", 150)
            session.boss_turns_taken = 0
            return f"🦅 **ВЗЛЁТ!** Дракон взмывает в небеса, становясь недосягаемым для ближнего боя! У вас есть {session.dragon_flight_timer} хода босса, чтобы нанести {session.dragon_flight_threshold} урона дальними атаками и сбить его!", ""
        else:
            boss_atk = session.boss_ultimate
            session.boss_turns_taken = 0
            is_ultimate = True

    # 3. Обычная атака босса
    else:
        valid_attacks = []
        for atk in session.boss_attacks:
            if atk.get("special") == "corpse_explosion":
                if len(skeletons) > 0:
                    valid_attacks.extend([atk, atk]) 
            else:
                valid_attacks.append(atk)
                
        boss_atk = random.choice(valid_attacks)
        session.boss_turns_taken += 1

    is_corpse_explosion = boss_atk.get("special") == "corpse_explosion"
    skel_count = len(skeletons) if is_corpse_explosion else 0

    targets = []
    if is_corpse_explosion:
        targets = alive_players
        atk_type_text = f"подрывая {skel_count} скелет(ов)"
        for sk in skeletons: 
            sk["is_skeleton"] = False
            if sk["id"] in session.turn_order:
                session.turn_order.remove(sk["id"])
    elif boss_atk["target"] == "aoe":
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
        if boss_atk.get("is_flight"):
             boss_atk_text = f"🌋 **АРМАГЕДДОН!** Вы не успели сбить Дракона! Он обрушивает **{boss_atk['name']}**!"
        else:
             boss_atk_text = f"🌟 **УЛЬТИМЕЙТ!** 👹 **{session.boss_name}** обрушивает {atk_type_text} **{boss_atk['name']}**!"
    else: 
        boss_atk_text = f"👹 **{session.boss_name}** проводит {atk_type_text} **{boss_atk['name']}**!"
    
    death_reports = ""
    total_heal = 0
    for t in targets:
        t_stats = database.get_total_stats(t["id"])
        if random.randint(1, 100) <= t_stats["DEX"]:
            boss_atk_text += f"\n💨 <@{t['id']}> **УКЛОНЯЕТСЯ** от атаки!"
            continue
            
        atk_mod = 1.0 - sum(b["value"] for b in session.boss_debuffs["atk_down"].values())
        atk_mod = max(0.1, atk_mod)
        
        if is_corpse_explosion:
            base_dmg = int((50 * skel_count) * atk_mod)
        else:
            base_dmg = int(random.randint(boss_atk["min_damage"], boss_atk["max_damage"]) * atk_mod)
        
        def_mod = 1.0
        for b in session.party_buffs["def"].values():
            def_mod *= (1.0 - b["value"])
            
        boss_damage = max(1, int(base_dmg * def_mod))
        
        t["hp"] = max(0, t["hp"] - boss_damage)
        boss_atk_text += f"\n💥 <@{t['id']}> получает **{boss_damage}** урона."

        if boss_atk.get("heal_pct") and boss_damage > 0:
            total_heal += int(boss_damage * boss_atk["heal_pct"])
        
        if boss_atk.get("effect") and t["hp"] > 0:
            stacks = boss_atk["effect"].get("stacks", 1)
            dur = boss_atk["effect"]["duration"]
            
            for _ in range(stacks):
                t["debuffs"].append({
                    "type": boss_atk["effect"]["type"], 
                    "duration": dur, 
                    "value": boss_atk["effect"].get("value", 0.30)
                })
            
            boss_atk_text += f" ☣️ Наложен эффект: {boss_atk['effect']['type']}!"

        if t["hp"] <= 0:
            t["is_alive"] = False
            if session.boss_name == "Проклятый Некромант": t["is_skeleton"] = True
            death_reports += f"\n💀 <@{t['id']}> погиб!"
            if not t.get("is_skeleton") and t["id"] in session.turn_order: 
                session.turn_order.remove(t["id"])

    if total_heal > 0:
        session.boss_hp = min(session.boss_max_hp, session.boss_hp + total_heal)
        boss_atk_text += f"\n🩸 Босс восстанавливает себе **{total_heal}** HP!"
        
    return boss_atk_text, death_reports