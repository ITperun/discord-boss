from game_state import session

def generate_status_text():
    text = "📋 **СОСТОЯНИЕ ПОЛЯ БОЯ:**\n"
    
    party_text = ""
    if session.party_buffs["atk"]:
        total = int(sum(b["value"] for b in session.party_buffs["atk"].values()) * 100)
        dur = max(b["duration"] for b in session.party_buffs["atk"].values())
        party_text += f"🟢 **Атака:** +{total}% (Ост: {dur} х.)\n"
    if session.party_buffs["def"]:
        total = int(sum(b["value"] for b in session.party_buffs["def"].values()) * 100)
        dur = max(b["duration"] for b in session.party_buffs["def"].values())
        party_text += f"🛡️ **Защита:** +{total}% (Ост: {dur} х.)\n"
    if session.party_buffs["regen"]:
        total = len(session.party_buffs["regen"]) * 7
        dur = max(b["duration"] for b in session.party_buffs["regen"])
        party_text += f"❤️ **Регенерация:** +{total} HP/ход (Ост: {dur} х.)\n"
    if session.party_buffs["vamp"]:
        dur = max(b["duration"] for b in session.party_buffs["vamp"].values())
        party_text += f"🦇 **Вампиризм:** Активен (Ост: {dur} х.)\n"
        
    if party_text: text += "\n👥 **Командные Эффекты:**\n" + party_text
    
    boss_text = ""
    if session.boss_ultimate:
        boss_text += f"🌟 **Зарядка Ультимейта:** {session.boss_turns_taken}/3\n"
    if session.boss_debuffs["def_down"]:
        total = int(sum(b["value"] for b in session.boss_debuffs["def_down"].values()) * 100)
        dur = max(b["duration"] for b in session.boss_debuffs["def_down"].values())
        boss_text += f"🔴 **Раскол брони:** -{total}% (Ост: {dur} х.)\n"
    if session.boss_debuffs["atk_down"]:
        total = int(sum(b["value"] for b in session.boss_debuffs["atk_down"].values()) * 100)
        dur = max(b["duration"] for b in session.boss_debuffs["atk_down"].values())
        boss_text += f"📉 **Слабость:** -{total}% урона (Ост: {dur} х.)\n"
    if session.boss_debuffs["dots"]:
        for d in session.boss_debuffs["dots"]:
            boss_text += f"🔥 **{d['type'].capitalize()}:** {d['damage']} урон/ход (Ост: {d['duration']} х.)\n"
            
    if boss_text: text += "\n👹 **Статус Босса:**\n" + boss_text
            
    player_text = ""
    for p in session.players.values():
        if not p["is_alive"]: continue
        
        p_effects = []
        for d in p["debuffs"]:
            p_effects.append(f"🤒 {d['type'].capitalize()} ({d['duration']}х)")
        if p.get("strafe_turns", 0) > 0:
            p_effects.append(f"🌪️ Стрейф ({p['strafe_turns']}х)")
            
        if p_effects:
            mention_or_name = p['name'] if p.get("is_npc") else f"<@{p['id']}>"
            player_text += f"👤 {mention_or_name}: " + ", ".join(p_effects) + "\n"
            
    if player_text: text += "\n🎯 **Персональные статусы:**\n" + player_text
    if not party_text and not boss_text and not player_text:
        text += "\n*Чистое поле (Эффектов нет)*\n"
        
    return text