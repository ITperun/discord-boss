import discord
from discord.ext import commands
import asyncio
import random
import os
import json
import io
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# Загружаем токен
load_dotenv()
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Глобальные переменные для конфигурации
CLASS_SKILLS = {}
BOSSES_LIST = []
VIEW_CONFIG = {}

def load_game_data():
    with open("skills.json", "r", encoding="utf-8") as f:
        skills_data = json.load(f)
    with open("bosses.json", "r", encoding="utf-8") as f:
        bosses_data = json.load(f)
    with open("view_config.json", "r", encoding="utf-8") as f:
        view_config = json.load(f)
    return skills_data, bosses_data, view_config

CLASS_SKILLS, BOSSES_LIST, VIEW_CONFIG = load_game_data()
AVAILABLE_CLASSES = list(CLASS_SKILLS.keys())

# === ✂️ НАРЕЗКА СПРАЙТОВ ===
def get_player_sprite(class_name):
    cfg = VIEW_CONFIG["spritesheet"]
    if not os.path.exists(cfg["path"]): return None
    try:
        sheet = Image.open(cfg["path"]).convert("RGBA")
        frame_w = sheet.width // cfg["columns"]
        frame_h = sheet.height // cfg["rows"]
        col, row = cfg["mapping"].get(class_name, (0,0))
        return sheet.crop((col * frame_w, row * frame_h, col * frame_w + frame_w, row * frame_h + frame_h))
    except Exception: return None

# === СЕССИЯ ИГРЫ ===
class GameSession:
    def __init__(self):
        self.state = "IDLE"
        self.players = {}
        self.boss_name = ""
        self.boss_hp = 0
        self.boss_max_hp = 0
        self.boss_base_def = 0.0
        self.boss_attacks = []
        self.turn_order = []
        
        # Индивидуальные стакающиеся баффы
        self.party_buffs = {"atk": {}, "def": {}, "regen": [], "vamp": {}}
        self.boss_debuffs = {"def_down": {}, "atk_down": {}, "dots": []}
        
        self.boss_cooldown_counter = 0
        self.boss_slow_stacks = 0

session = GameSession()

# === 🎉 ОРИГИНАЛЬНАЯ ФУНКЦИЯ ГЕНЕРАЦИИ ПОЛЯ БОЯ ===
def generate_battle_image(current_player_id=None, boss_action_ready=False):
    boss_cfg = VIEW_CONFIG["boss_display"]
    party_cfg = VIEW_CONFIG["party_display"]

    try:
        bg = Image.open("assets/background.png").convert("RGBA")
    except FileNotFoundError:
        bg = Image.new("RGBA", (800, 400), (40, 40, 40, 255))
        
    draw = ImageDraw.Draw(bg)
    
    try:
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        font_hp = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
    except IOError:
        font_name = ImageFont.load_default()
        font_hp = ImageFont.load_default()

    # Отрисовка босса
    boss_filename = f"assets/{session.boss_name.lower().replace(' ', '-')}.png"
    if not os.path.exists(boss_filename):
        boss_filename = "assets/boss.png"

    boss_x, boss_y = boss_cfg["pos_x"], boss_cfg["pos_y"]
    
    try:
        boss_img = Image.open(boss_filename).convert("RGBA")
        aspect = boss_img.width / boss_img.height
        boss_w = int(boss_cfg["target_height"] * aspect)  
        boss_h = boss_cfg["target_height"]
        
        boss_img = boss_img.resize((boss_w, boss_h), Image.Resampling.NEAREST)
        bg.paste(boss_img, (boss_x, boss_y), boss_img)
    except FileNotFoundError:
        boss_w, boss_h = boss_cfg["default_width"], boss_cfg["default_height"]
        draw.rectangle([boss_x, boss_y, boss_x + boss_w, boss_y + boss_h], fill=(200, 50, 50, 255))
    
    # Тексты босса
    total_def = session.boss_base_def - sum(b["value"] for b in session.boss_debuffs["def_down"].values())
    alive_count = len([p for p in session.players.values() if p["is_alive"]])
    max_cd = 3 if alive_count >= 5 else 2 if alive_count >= 3 else 1
    
    draw.text((boss_x, boss_y - 60), f"👹 {session.boss_name} (🛡️ Защита: {int(total_def*100)}%)", fill="white", font=font_name)
    cd_text = "⚠️ ПОДГОТОВКА УДАРА!" if boss_action_ready else f"⏳ Зарядка атаки: {session.boss_cooldown_counter}/{max_cd}"
    draw.text((boss_x, boss_y - 45), cd_text, fill="orange" if boss_action_ready else "#87CEEB", font=font_name)
    
    # Полоска ХП босса
    draw.rectangle([boss_x, boss_y - 20, boss_x + boss_w, boss_y - 10], fill=(60, 20, 20))
    hp_percent = session.boss_hp / session.boss_max_hp
    draw.rectangle([boss_x, boss_y - 20, boss_x + int(boss_w * hp_percent), boss_y - 10], fill=(220, 40, 40))
    draw.text((boss_x + 5, boss_y - 21), f"{session.boss_hp} / {session.boss_max_hp} HP", fill="white", font=font_hp)

    # Отрисовка отряда на основе оригинальных параметров
    p_w, p_h = party_cfg["sprite_width"], party_cfg["sprite_height"]
    start_x = party_cfg["start_x"]
    spacing_x = party_cfg["spacing_x"]
    base_y = party_cfg["base_y"]

    for idx, p_id in enumerate(reversed(session.turn_order)):
        player = session.players[p_id]
        if not player["is_alive"]: continue
            
        real_idx = len(session.turn_order) - 1 - idx
        x = start_x + (real_idx * spacing_x)
        y = base_y - (real_idx * party_cfg["perspective_step_y"])

        if p_id == current_player_id:
            x -= party_cfg["attacker_advance_x"]
            y += party_cfg["attacker_advance_y"]
            
        p_img = get_player_sprite(player['class'])
        if p_img is not None:
            p_img = p_img.resize((p_w, p_h), Image.Resampling.NEAREST)
            bg.paste(p_img, (x, y), p_img)
        else:
            color = (80, 80, 220) if player['class'] == 'бард' else (220, 180, 60)
            draw.rectangle([x, y, x + p_w, y + p_h], fill=color)

        name_color = "#FFD700" if p_id == current_player_id else "white"
        p_name = player["name"][:10] + (" [С]" if player.get("strafe_turns", 0) > 0 else "")
        
        draw.text((x, y - 35), p_name, fill=name_color, font=font_name)
        draw.rectangle([x, y - 15, x + p_w, y - 8], fill=(60, 20, 20))
        p_hp_percent = player["hp"] / 100
        draw.rectangle([x, y - 15, x + int(p_w * p_hp_percent), y - 8], fill=(40, 220, 40))

    img_byte_arr = io.BytesIO()
    bg.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return discord.File(fp=img_byte_arr, filename="battle.png")

# === СООБЩЕНИЕ СО СТАТУСАМИ ===
def generate_status_text():
    text = "📋 **СОСТОЯНИЕ ПОЛЯ БОЯ:**\n"
    if session.party_buffs["atk"]:
        total = int(sum(b["value"] for b in session.party_buffs["atk"].values()) * 100)
        dur = max(b["duration"] for b in session.party_buffs["atk"].values())
        text += f"🟢 **Атака отряда:** +{total}% (Осталось ходов: {dur})\n"
    if session.party_buffs["def"]:
        total = int(sum(b["value"] for b in session.party_buffs["def"].values()) * 100)
        dur = max(b["duration"] for b in session.party_buffs["def"].values())
        text += f"🛡️ **Защита отряда:** +{total}% (Осталось ходов: {dur})\n"
    if session.party_buffs["regen"]:
        total = len(session.party_buffs["regen"]) * 7
        dur = max(b["duration"] for b in session.party_buffs["regen"])
        text += f"❤️ **Регенерация:** +{total} HP/ход (Осталось ходов: {dur})\n"
    if session.party_buffs["vamp"]:
        dur = max(b["duration"] for b in session.party_buffs["vamp"].values())
        text += f"🦇 **Вампиризм:** Активен (Осталось ходов: {dur})\n"
    
    if session.boss_debuffs["def_down"]:
        total = int(sum(b["value"] for b in session.boss_debuffs["def_down"].values()) * 100)
        dur = max(b["duration"] for b in session.boss_debuffs["def_down"].values())
        text += f"🔴 **Раскол брони босса:** -{total}% (Осталось ходов: {dur})\n"
    if session.boss_debuffs["atk_down"]:
        total = int(sum(b["value"] for b in session.boss_debuffs["atk_down"].values()) * 100)
        dur = max(b["duration"] for b in session.boss_debuffs["atk_down"].values())
        text += f"📉 **Слабость босса:** -{total}% урона (Осталось ходов: {dur})\n"
    if session.boss_debuffs["dots"]:
        for d in session.boss_debuffs["dots"]:
            text += f"🔥 **{d['type'].capitalize()} на боссе:** {d['damage']} урон/ход (Осталось ходов: {d['duration']})\n"
            
    # Собираем дебаффы, которые висят на игроках
    player_debuffs = {}
    for p in session.players.values():
        if p["is_alive"]:
            for d in p["debuffs"]:
                if d["type"] not in player_debuffs or d["duration"] > player_debuffs[d["type"]]:
                    player_debuffs[d["type"]] = d["duration"]
                    
    for dtype, dur in player_debuffs.items():
        text += f"🤒 **Дебафф на отряде ({dtype.capitalize()}):** Осталось ходов: {dur}\n"
            
    if "\n" not in text[25:]: text += "*Эффектов нет*\n"
    return text

# === МЕНЮ ВЫБОРА ЦЕЛИ ===
class TargetSelect(discord.ui.Select):
    def __init__(self, player, skill, allies):
        opts = [discord.SelectOption(label=a["name"], description=f"Класс: {a['class']} | HP: {a['hp']}", value=str(a["id"])) for a in allies]
        super().__init__(placeholder="Выберите союзника...", options=opts)
        self.player, self.skill = player, skill

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.player["id"]):
            await interaction.response.send_message("❌ Не ваш ход!", ephemeral=True)
            return
        self.view.chosen_target = self.values[0]
        self.view.stop()
        await interaction.response.defer()

class TargetView(discord.ui.View):
    def __init__(self, player, skill, allies, timeout=30):
        super().__init__(timeout=timeout)
        self.chosen_target = None
        self.add_item(TargetSelect(player, skill, allies))

# === КНОПКИ ДЕЙСТВИЙ ИГРОКА ===
class TurnButtons(discord.ui.View):
    def __init__(self, player, timeout=30):
        super().__init__(timeout=timeout)
        self.player = player
        self.chosen_skill = None
        for skill in CLASS_SKILLS.get(player["class"], []):
            btn = discord.ui.Button(label=skill["name"], custom_id=skill["id"], style=discord.ButtonStyle.primary)
            btn.callback = self.make_callback(skill)
            self.add_item(btn)
        info_btn = discord.ui.Button(label="ℹ️ Описание", custom_id=f"info_{player['id']}", style=discord.ButtonStyle.secondary)
        info_btn.callback = self.show_skills_info
        self.add_item(info_btn)

    def make_callback(self, skill):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != str(self.player["id"]): return await interaction.response.send_message("❌ Не ваш ход!", ephemeral=True)
            self.chosen_skill = skill
            for item in self.children: item.disabled = True
            await interaction.response.defer()
            self.stop()
        return callback

    async def show_skills_info(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.player["id"]): return
        text = f"📖 **Шпаргалка [{self.player['class'].upper()}]:**\n\n"
        for s in CLASS_SKILLS.get(self.player["class"], []): text += f"• **{s['name']}**\n  └ *{s.get('desc', '')}*\n\n"
        await interaction.response.send_message(text, ephemeral=True)


@bot.event
async def on_ready(): print(f'✅ Бот {bot.user} запущен!')

# === ОСНОВНОЙ ЦИКЛ БОЯ ===
@bot.command(name="старт")
async def start_boss(ctx):
    global session, CLASS_SKILLS, BOSSES_LIST, VIEW_CONFIG
    CLASS_SKILLS, BOSSES_LIST, VIEW_CONFIG = load_game_data()
    
    if session.state != "IDLE": return await ctx.send("⚠️ Битва уже идет!")

    boss = random.choice(BOSSES_LIST)
    session.__init__()
    session.state = "RECRUITING"
    session.boss_name, session.boss_hp, session.boss_max_hp = boss["name"], boss["hp"], boss["hp"]
    session.boss_base_def, session.boss_attacks = boss.get("defense", 0.0), boss.get("attacks", [])
    
    await ctx.send(f"🚨 **Появился босс: {session.boss_name} [❤️ {session.boss_hp} HP]!**\nПишите: `!присоединиться [класс]`")
    await asyncio.sleep(60)

    if len(session.players) == 0:
        session.state = "IDLE"
        return await ctx.send("😔 Никто не пришел.")

    for i in range(1, 8 - len(session.players)):
        bot_id = f"npc_bot{i}"
        session.players[bot_id] = {"id": bot_id, "name": bot_id, "class": random.choice(AVAILABLE_CLASSES), "hp": 100, "is_alive": True, "is_npc": True, "strafe_turns": 0, "debuffs": []}

    session.state = "BATTLING"
    session.turn_order = list(session.players.keys())
    random.shuffle(session.turn_order)
    
    battle_msg = await ctx.send(content="⚔️ **Битва начинается!**", file=generate_battle_image())
    status_msg = await ctx.send(content=generate_status_text())
    await asyncio.sleep(2)

    while session.boss_hp > 0:
        if not [p for p in session.players.values() if p["is_alive"]]: break

        # Безопасное получение текущего игрока
        if not session.turn_order: break
        p_id = session.turn_order[0]
        player = session.players[p_id]
        
        if not player["is_alive"]:
            session.turn_order.pop(0)
            continue

        action_text, tick_text, dmg = "", "", 0
        is_ode = False
        boss_trigger = False

        if player.get("is_npc"):
            skill = random.choice(CLASS_SKILLS[player["class"]])
            await battle_msg.edit(content=f"🤖 **Ходит {player['name']} ({player['class']}).**", attachments=[generate_battle_image(p_id)], view=None)
            await asyncio.sleep(1.5)
        else:
            view = TurnButtons(player)
            await battle_msg.edit(content=f"🛑 **Ход <@{player['id']}> ({player['class']}).** Выберите навык:", attachments=[generate_battle_image(p_id)], view=view)
            await view.wait()
            skill = view.chosen_skill
            
        target_id = None
        if skill and skill.get("target") == "ally":
            if player.get("is_npc"):
                allies = [p for p in session.players.values() if p["is_alive"] and p["id"] != p_id]
                target_id = str(random.choice(allies)["id"]) if allies else None
            else:
                allies = [p for p in session.players.values() if p["is_alive"] and (skill["id"] != "bard_ode" or str(p["id"]) != str(p_id))]
                if allies:
                    t_view = TargetView(player, skill, allies)
                    await battle_msg.edit(content=f"🎯 Выберите цель для **{skill['name']}**:", view=t_view)
                    await t_view.wait()
                    target_id = str(t_view.chosen_target) if t_view.chosen_target else None

        if skill is None:
            action_text += f"\n💤 Пропустил свой ход!"
        else:
            sid = skill["id"]
            action_text += f"\nИспользует **{skill['name']}**"
            
            base_dmg = 0
            if sid == "warrior_execute": base_dmg = random.randint(79, 80) if session.boss_hp < session.boss_max_hp/2 else random.randint(39, 40)
            elif sid in ["mage_fireball", "mage_ice"]: base_dmg = random.randint(29, 45)
            elif sid == "mage_lightning": base_dmg = random.randint(45, 60)
            elif sid in ["bard_solo", "priest_smite"]: base_dmg = random.randint(15, 25)
            elif sid == "ranger_shot": base_dmg = random.randint(45, 65)
            elif sid == "necro_touch": base_dmg = random.randint(15, 35)

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
                    if player["hp"] == 0: player["is_alive"] = False
            elif sid == "mage_fireball" and random.random() < 0.9: session.boss_debuffs["dots"].append({"type": "горение", "damage": 9, "duration": 3}); action_text += " 🔥 Босс подожжен!"
            elif sid == "mage_ice" and random.random() < 0.9:
                if session.boss_slow_stacks >= 2: action_text += " ❌ У босса иммунитет ко льду!"
                else: session.boss_slow_stacks += 1; session.boss_cooldown_counter = max(0, session.boss_cooldown_counter - 1); action_text += " ❄️ Зарядка заморожена!"
            elif sid == "mage_lightning" and random.random() < 0.3: player["hp"] = max(1, player["hp"] - 30); action_text += "\n⚠️ Маг теряет 30 HP от перегрузки!"
            elif sid == "bard_regen": session.party_buffs["regen"].append({"duration": 4}); session.party_buffs["atk"]["bard_regen"] = {"value": 0.10, "duration": 4}; action_text += " 🎺 Атака и реген отряда!"
            elif sid == "bard_ode" and target_id: 
                session.party_buffs["atk"]["bard_ode"] = {"value": 0.20, "duration": 4}
                if target_id in session.turn_order: session.turn_order.remove(target_id)
                session.turn_order.insert(1, target_id)
                action_text += " 🎸 Цель получает ход вне очереди!"
                is_ode = True
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

        # === 🔄 ГЛОБАЛЬНЫЙ ТИК ХОДА (1 кнопка = 1 ход) ===
        if not is_ode and session.boss_hp > 0:
            # Снижаем таймеры баффов отряда
            for cat in ["atk", "def", "vamp"]:
                for sid_key in list(session.party_buffs[cat].keys()):
                    session.party_buffs[cat][sid_key]["duration"] -= 1
                    if session.party_buffs[cat][sid_key]["duration"] <= 0: del session.party_buffs[cat][sid_key]
                    
            # Снижаем таймеры дебаффов босса
            for cat in ["def_down", "atk_down"]:
                for sid_key in list(session.boss_debuffs[cat].keys()):
                    session.boss_debuffs[cat][sid_key]["duration"] -= 1
                    if session.boss_debuffs[cat][sid_key]["duration"] <= 0: del session.boss_debuffs[cat][sid_key]

            # Регенерация
            regen_heal = len(session.party_buffs["regen"]) * 7
            if regen_heal > 0:
                for p in session.players.values():
                    if p["is_alive"]: p["hp"] = min(100, p["hp"] + regen_heal)
                tick_text += f"\n💚 Реген: отряд восстановил {regen_heal} HP."
            for r in session.party_buffs["regen"]: r["duration"] -= 1
            session.party_buffs["regen"] = [r for r in session.party_buffs["regen"] if r["duration"] > 0]
            
            # Доты на боссе (урон каждый ход!)
            dot_dmg = sum(d["damage"] for d in session.boss_debuffs["dots"])
            if dot_dmg > 0:
                session.boss_hp = max(0, session.boss_hp - dot_dmg)
                tick_text += f"\n🔥 Босс получает {dot_dmg} период. урона."
            for d in session.boss_debuffs["dots"]: d["duration"] -= 1
            session.boss_debuffs["dots"] = [d for d in session.boss_debuffs["dots"] if d["duration"] > 0]
            
            # Дебаффы на игроках (яд/горение)
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
                
            # Авто-стрейф Рейнджера
            for p in session.players.values():
                if p["is_alive"] and p.get("strafe_turns", 0) > 0:
                    boss_def = session.boss_base_def - sum(b["value"] for b in session.boss_debuffs["def_down"].values())
                    dmg1 = max(1, int(random.randint(10,15) * (1.0 - boss_def)))
                    dmg2 = max(1, int(random.randint(10,15) * (1.0 - boss_def)))
                    session.boss_hp = max(0, session.boss_hp - (dmg1 + dmg2))
                    tick_text += f"\n🏹 Авто-Стрейф ({p['name']}) наносит {dmg1} и {dmg2} урона!"
                    p["strafe_turns"] -= 1
                    
            # Счетчик ходов босса
            alive_count = len([p for p in session.players.values() if p["is_alive"]])
            max_cd = 3 if alive_count >= 5 else 2 if alive_count >= 3 else 1
            session.boss_cooldown_counter += 1
            if session.boss_cooldown_counter >= max_cd:
                boss_trigger = True
                session.boss_cooldown_counter = 0

        # Аккуратное смещение очереди
        if session.turn_order and session.turn_order[0] == p_id:
            popped = session.turn_order.pop(0)
            if player["is_alive"]: session.turn_order.append(popped)
        
        await battle_msg.edit(content=f"⚔️ <@{p_id}> {action_text}{tick_text} (У босса: {session.boss_hp} HP)", attachments=[generate_battle_image(None, boss_trigger)], view=None)
        await status_msg.edit(content=generate_status_text())
        await asyncio.sleep(5.0)

        if session.boss_hp <= 0: break

        # ================= ХОД БОССА =================
        if boss_trigger:
            alive_players = [p for p in session.players.values() if p["is_alive"]]
            if not alive_players: break
                
            boss_atk = random.choice(session.boss_attacks)
            targets = alive_players if boss_atk["target"] == "aoe" else [random.choice(alive_players)]
            boss_atk_text = f"👹 **{session.boss_name}** проводит {'AOE' if boss_atk['target']=='aoe' else 'точечную'} атаку **{boss_atk['name']}**!"
            
            death_reports = ""
            for t in targets:
                atk_mod = 1.0 - sum(b["value"] for b in session.boss_debuffs["atk_down"].values())
                base_dmg = int(random.randint(boss_atk["min_damage"], boss_atk["max_damage"]) * max(0.1, atk_mod))
                def_mod = 1.0 - sum(b["value"] for b in session.party_buffs["def"].values())
                boss_damage = max(1, int(base_dmg * def_mod))
                
                t["hp"] = max(0, t["hp"] - boss_damage)
                boss_atk_text += f"\n💥 <@{t['id']}> получает **{boss_damage}** урона."
                
                if boss_atk.get("effect") and t["hp"] > 0:
                    t["debuffs"].append({"type": boss_atk["effect"]["type"], "duration": boss_atk["effect"]["duration"], "value": boss_atk["effect"].get("value", 0.30)})
                    boss_atk_text += f" ☣️ Наложен эффект: {boss_atk['effect']['type']}!"

                if t["hp"] <= 0:
                    t["is_alive"] = False; death_reports += f"\n💀 <@{t['id']}> погиб!"
                    if t["id"] in session.turn_order: session.turn_order.remove(t["id"])

            await battle_msg.edit(content=f"{boss_atk_text}{death_reports}", attachments=[generate_battle_image()], view=None)
            await status_msg.edit(content=generate_status_text())
            await asyncio.sleep(5.0)

    if session.boss_hp <= 0: await battle_msg.edit(content=f"🎉 **ПОБЕДА!** **{session.boss_name}** повержен! 🏆", attachments=[generate_battle_image()], view=None)
    else: await battle_msg.edit(content=f"💀 **ПОРАЖЕНИЕ...** Отряд уничтожен.", attachments=[generate_battle_image()], view=None)
    session.state = "IDLE"

@bot.command(name="присоединиться", aliases=["join"])
async def join_game(ctx, role: str = None):
    if session.state != "RECRUITING": return
    if not role or role.lower() not in AVAILABLE_CLASSES: return await ctx.send(f"❌ Классы: {', '.join(AVAILABLE_CLASSES)}")
    if str(ctx.author.id) in session.players: return
    session.players[str(ctx.author.id)] = {"id": ctx.author.id, "name": ctx.author.display_name, "class": role.lower(), "hp": 100, "is_alive": True, "is_npc": False, "strafe_turns": 0, "debuffs": []}
    await ctx.send(f"✅ {ctx.author.mention} готов как **{role}**!")

bot.run(os.getenv('DISCORD_TOKEN'))