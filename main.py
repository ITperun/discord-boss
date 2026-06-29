import discord
from discord.ext import commands
import asyncio
import random
import os
import json
import io
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# Загружаем токен из скрытого файла .env
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

battle_message = None

def load_game_data():
    with open("skills.json", "r", encoding="utf-8") as f:
        skills_data = json.load(f)
    with open("bosses.json", "r", encoding="utf-8") as f:
        bosses_data = json.load(f)
    return skills_data, bosses_data

# Загружаем конфигурацию
CLASS_SKILLS, BOSSES_LIST = load_game_data()
AVAILABLE_CLASSES = list(CLASS_SKILLS.keys())

# === ✂️ СИСТЕМА ДИНАМИЧЕСКОЙ НАРЕЗКИ СПРАЙТОВ ИГРОКОВ ===
def get_player_sprite(class_name):
    sheet_path = "assets/маг, воин, священник, рейнджер, бард, некромант.png"
    if not os.path.exists(sheet_path):
        return None
        
    try:
        sheet = Image.open(sheet_path).convert("RGBA")
        
        # Определяем размеры одного кадра (сетка 3x2)
        frame_w = sheet.width // 3
        frame_h = sheet.height // 2
        
        # Маппинг классов на координаты сетки (колонка, строка)
        class_coords = {
            "маг": (0, 0),
            "воин": (1, 0),
            "священник": (2, 0),
            "рейнджер": (0, 1),
            "бард": (1, 1),
            "некромант": (2, 1)
        }
        
        if class_name not in class_coords:
            return None
            
        col, row = class_coords[class_name]
        
        # Вырезаем квадрат персонажа
        left = col * frame_w
        top = row * frame_h
        right = left + frame_w
        bottom = top + frame_h
        
        sprite = sheet.crop((left, top, right, bottom))
        return sprite
    except Exception as e:
        print(f"Ошибка нарезки спрайта: {e}")
        return None

class GameSession:
    def __init__(self):
        self.state = "IDLE"
        self.players = {}
        self.boss_name = ""
        self.boss_hp = 0
        self.boss_max_hp = 0
        self.boss_attacks = []
        self.boss_phys_def = 0.0
        self.boss_mag_def = 0.0
        self.turn_order = []
        
        # БАФФЫ КОМАНДЫ
        self.atk_buff_value = 0.0   
        self.atk_buff_turns = 0     
        self.def_buff_value = 0.0   
        self.def_buff_turns = 0     
        
        # СЧЕТЧИКИ БОССА
        self.boss_cooldown_counter = 0
        self.boss_slow_stacks = 0
        self.boss_debuffs = []

session = GameSession()

# === 🎉 ФУНКЦИЯ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЯ БИТВЫ ===
def generate_battle_image(current_player_id=None, boss_action_ready=False):
    try:
        bg = Image.open("assets/background.png").convert("RGBA")
    except FileNotFoundError:
        bg = Image.new("RGBA", (800, 400), (40, 40, 40, 255))
        
    draw = ImageDraw.Draw(bg)
    
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font_name = ImageFont.truetype(font_path, 12)
        font_hp = ImageFont.truetype(font_path, 10)
    except IOError:
        font_name = ImageFont.load_default()
        font_hp = ImageFont.load_default()

    # Динамическая загрузка уникального ассета босса
    boss_filename = f"assets/{session.boss_name.lower().replace(' ', '-')}.png"
    if not os.path.exists(boss_filename):
        boss_filename = "assets/boss.png"

    boss_y = 160
    
    try:
        boss_img = Image.open(boss_filename).convert("RGBA")
        
        # 📐 АВТОМАТИЧЕСКИЙ РАСЧЕТ ПРОПОРЦИЙ БОССА
        boss_target_h = 200  # Желаемая высота босса на экране
        aspect = boss_img.width / boss_img.height
        boss_w = int(boss_target_h * aspect)  # Ширина подстроится автоматически
        boss_h = boss_target_h
        
        # Центрируем босса по левой стороне тропинки (базовая позиция по X = 40)
        # Если босс широкий, он расширится вправо, не ломая левый край
        boss_x = 40
        
        boss_img = boss_img.resize((boss_w, boss_h), Image.Resampling.NEAREST)
        bg.paste(boss_img, (boss_x, boss_y), boss_img)
    except FileNotFoundError:
        boss_w, boss_h = 200, 200
        boss_x = 40
        draw.rectangle([boss_x, boss_y, boss_x + boss_w, boss_y + boss_h], fill=(200, 50, 50, 255))
    
    # Индикатор ярости/подготовки атаки босса (выровнен по boss_x)
    alive_count = len([p for p in session.players.values() if p["is_alive"]])
    if alive_count >= 5: current_max_cd = 3
    elif alive_count >= 3: current_max_cd = 2
    else: current_max_cd = 1
    
    cd_text = "⚠️ ПОДГОТОВКА УДАРА!" if boss_action_ready else f"⏳ Зарядка атаки: {session.boss_cooldown_counter}/{current_max_cd}"
    
    draw.text((boss_x, boss_y - 60), f"{session.boss_name} (🛡️{int(session.boss_phys_def*100)}% 🔮{int(session.boss_mag_def*100)}%)", fill="white", font=font_name)
    draw.text((boss_x, boss_y - 45), cd_text, fill="orange" if boss_action_ready else "#87CEEB", font=font_name)
    
    # Полоска ХП босса (подстраивается под его динамическую ширину boss_w)
    draw.rectangle([boss_x, boss_y - 20, boss_x + boss_w, boss_y - 10], fill=(60, 20, 20))
    hp_percent = session.boss_hp / session.boss_max_hp
    draw.rectangle([boss_x, boss_y - 20, boss_x + int(boss_w * hp_percent), boss_y - 10], fill=(220, 40, 40))
    draw.text((boss_x + 5, boss_y - 21), f"{session.boss_hp} / {session.boss_max_hp}", fill="white", font=font_hp)

    if session.boss_debuffs:
        debuff_txt = "Эффекты: " + ", ".join([f"{d['type']}({d['duration']}т)" for d in session.boss_debuffs])
        draw.text((boss_x, boss_y - 5), debuff_txt, fill="#FF6347", font=font_hp)

    # Отображение баффов команды
    buff_y = 20
    if session.atk_buff_turns > 0:
        draw.text((320, buff_y), f"⚔️ Атака: +{int(session.atk_buff_value*100)}% ({session.atk_buff_turns}х)", fill="#FFD700", font=font_name)
        buff_y += 20
    if session.def_buff_turns > 0:
        draw.text((320, buff_y), f"🛡️ Щит: +{int(session.def_buff_value*100)}% ({session.def_buff_turns}х)", fill="#00FFFF", font=font_name)

    # Отрисовка отряда участников (📏 ровно 10 пикселей чистого зазора по горизонтали) позиция
    p_w, p_h = 75, 75       
    start_x = 480           
    spacing_x = 85
    base_y = 235           

    for idx, p_id in enumerate(reversed(session.turn_order)):
        player = session.players[p_id]
        if not player["is_alive"]:
            continue
            
        real_idx = len(session.turn_order) - 1 - idx
        is_his_turn = (p_id == current_player_id)
        
        x = start_x + (real_idx * spacing_x)
        y = base_y - (real_idx * 5)

        if is_his_turn:
            x -= 30  
            y += 15  
            
        p_img = get_player_sprite(player['class'])
        
        if p_img is not None:
            p_img = p_img.resize((p_w, p_h), Image.Resampling.NEAREST)
            bg.paste(p_img, (x, y), p_img)
        else:
            color = (80, 80, 220) if player['class'] == 'бард' else (220, 180, 60)
            draw.rectangle([x, y, x + p_w, y + p_h], fill=color)

        display_name = player["name"][:10]
        name_color = "#FFD700" if is_his_turn else "white"
        
        p_debuffs = player.get("debuffs", [])
        if p_debuffs:
            display_name += f" [{p_debuffs[0]['type'][:3]}]"

        draw.text((x, y - 35), display_name, fill=name_color, font=font_name)
        draw.rectangle([x, y - 15, x + p_w, y - 8], fill=(60, 20, 20))
        p_hp_percent = player["hp"] / 100
        draw.rectangle([x, y - 15, x + int(p_w * p_hp_percent), y - 8], fill=(40, 220, 40))

    img_byte_arr = io.BytesIO()
    bg.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return discord.File(fp=img_byte_arr, filename="battle.png")


# === ℹ️ ИНТЕРАКТИВНЫЕ КНОПКИ С СКРЫТЫМ ОПИСАНИЕМ НАВЫКОВ ===
class TurnButtons(discord.ui.View):
    def __init__(self, player, timeout=30):
        super().__init__(timeout=timeout)
        self.player = player
        self.chosen_skill = None
        
        player_class = player["class"]
        skills = CLASS_SKILLS.get(player_class, [])
        
        # Кнопки боевых навыков
        for skill in skills:
            button = discord.ui.Button(
                label=skill["name"], 
                custom_id=skill["id"], 
                style=discord.ButtonStyle.primary
            )
            button.callback = self.make_callback(skill)
            self.add_item(button)
            
        # Дополнительная кнопка скрытой персональной подсказки
        info_button = discord.ui.Button(
            label="ℹ️ Описание навыков",
            custom_id=f"info_{player['id']}",
            style=discord.ButtonStyle.secondary
        )
        info_button.callback = self.show_skills_info
        self.add_item(info_button)

    def make_callback(self, skill):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != str(self.player["id"]):
                await interaction.response.send_message("❌ Сейчас не ваш ход!", ephemeral=True)
                return
                
            self.chosen_skill = skill
            for item in self.children:
                item.disabled = True
                
            await interaction.response.defer()
            self.stop()
            
        return callback

    # Функция отправки эфемерального (скрытого) сообщения
    async def show_skills_info(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.player["id"]):
            await interaction.response.send_message("❌ Вы можете смотреть описание только в свой ход!", ephemeral=True)
            return
            
        player_class = self.player["class"]
        skills = CLASS_SKILLS.get(player_class, [])
        
        info_text = f"📖 **Шпаргалка по навыкам класса [{player_class.upper()}]:**\n\n"
        for s in skills:
            dmg_icon = "🗡️" if s.get("dmg_type") == "physical" else "🔮"
            info_text += f"• **{s['name']}**\n"
            info_text += f"  └ Базовый урон: {s.get('damage', 0)} {dmg_icon if s.get('damage', 0) > 0 else ''}\n"
            if s.get('heal', 0) > 0:
                info_text += f"  └ Исцеление команды: +{s['heal']} ❤️\n"
            if s.get("buff_turns", 0) > 0:
                if s.get("buff_atk_pct", 0) > 0:
                    info_text += f"  └ Бафф: +{int(s['buff_atk_pct']*100)}% к атаке на {s['buff_turns']}х.\n"
                if s.get("buff_def_pct", 0) > 0:
                    info_text += f"  └ Бафф: +{int(s['buff_def_pct']*100)}% к щиту на {s['buff_turns']}х.\n"
            if s.get("debuff"):
                info_text += f"  └ Эффект дебаффа: [{s['debuff']['type']}] на {s['debuff']['duration']} тиков.\n"
            info_text += f"  └ *Описание: {s.get('desc', 'Описание отсутствует')}*\n\n"
            
        await interaction.response.send_message(info_text, ephemeral=True)

    async def on_timeout(self):
        self.stop()


@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен и готов к RPG рейдам!')

@bot.command(name="старт")
async def start_boss(ctx):
    """Команда для запуска пошагового боя с яростью босса и анти-абузом"""
    global session, BOSSES_LIST, CLASS_SKILLS, battle_message
    
    CLASS_SKILLS, BOSSES_LIST = load_game_data()
    
    if session.state != "IDLE":
        await ctx.send("⚠️ Битва или сбор уже идут!")
        return

    current_boss = random.choice(BOSSES_LIST)
    
    session.state = "RECRUITING"
    session.players.clear()
    session.boss_name = current_boss["name"]
    session.boss_hp = current_boss["hp"]
    session.boss_max_hp = current_boss["hp"]
    session.boss_attacks = current_boss.get("attacks", [])
    session.boss_phys_def = current_boss.get("physical_def", 0.0)
    session.boss_mag_def = current_boss.get("magical_def", 0.0)
    session.boss_debuffs.clear()
    
    # Сброс таймеров и накопления иммунитета
    session.boss_cooldown_counter = 0
    session.boss_slow_stacks = 0
    session.atk_buff_value = 0.0
    session.atk_buff_turns = 0
    session.def_buff_value = 0.0
    session.def_buff_turns = 0
    
    await ctx.send(
        f"🚨 **ВНИМАНИЕ! Появился босс: {session.boss_name} [❤️ {session.boss_hp} HP]!** 🚨\n"
        f"У вас есть 1 минута, чтобы присоединиться!\n"
        f"Пишите: `!присоединиться [класс]`"
    )

    await asyncio.sleep(60)

    real_players_count = len(session.players)
    if real_players_count == 0:
        session.state = "IDLE"
        await ctx.send(f"😔 Никто из игроков не пришел на битву. Рейд отменен.")
        return

    # Заполняем лобби ботами ровно до 7 участников
    total_slots = 7
    if real_players_count < total_slots:
        needed_bots = total_slots - real_players_count
        for i in range(1, needed_bots + 1):
            bot_id = f"npc_bot{i}"
            bot_class = random.choice(AVAILABLE_CLASSES)
            session.players[bot_id] = {
                "id": bot_id,
                "name": f"npc_bot{i}",
                "class": bot_class,
                "hp": 100,
                "is_alive": True,
                "is_npc": True,
                "debuffs": []
            }

    session.state = "BATTLING"
    session.turn_order = list(session.players.keys())
    random.shuffle(session.turn_order)
    
    img_file = generate_battle_image()
    battle_message = await ctx.send(content="⚔️ **Битва начинается! Подготовка поля боя...**", file=img_file)
    await asyncio.sleep(2)

    round_number = 1
    while session.boss_hp > 0:
        alive_players = [p for p in session.players.values() if p["is_alive"]]
        if not alive_players:
            break

        p_id = session.turn_order[0]
        player = session.players[p_id]
        
        if not player["is_alive"]:
            session.turn_order.append(session.turn_order.pop(0))
            continue
            
        # === ⏳ ТИКИ ДЕБАФФОВ НА НАЧАЛО ХОДА ИГРОКА ===
        debuff_damage = 0
        debuff_notes = ""
        active_p_debuffs = player.get("debuffs", [])
        for debuff in list(active_p_debuffs):
            if debuff["type"] in ["горение", "отравление"]:
                debuff_damage += debuff["damage"]
                debuff_notes += f"\n🔥/🦨 Дебафф наносит {player['name']} **{debuff['damage']}** урона."
            debuff["duration"] -= 1
            if debuff["duration"] <= 0:
                active_p_debuffs.remove(debuff)
                debuff_notes += f"\n✨ Эффект [{debuff['type']}] на {player['name']} рассеялся."

        player["hp"] = max(0, player["hp"] - debuff_damage)
        if player["hp"] <= 0:
            player["is_alive"] = False
            if player["id"] in session.turn_order: session.turn_order.remove(player["id"])
            img_file = generate_battle_image(current_player_id=None)
            await battle_message.edit(content=f"💀 {player['name']} погиб от периодического урона дебаффов!{debuff_notes}", attachments=[img_file], view=None)
            await asyncio.sleep(5.0)
            continue

        img_file = generate_battle_image(current_player_id=p_id)
        chosen_skill = None
        
        if player.get("is_npc"):
            available_npc_skills = CLASS_SKILLS.get(player["class"], [])
            chosen_skill = random.choice(available_npc_skills)
            await battle_message.edit(
                content=f"🔹 **--- ХОД ОТРЯДА ---** 🔹{debuff_notes}\n🤖 **Ходит {player['name']} ({player['class']}).** Выбирает заклинание...",
                attachments=[img_file], view=None
            )
            await asyncio.sleep(1.5)
        else:
            view = TurnButtons(player, timeout=30)
            await battle_message.edit(
                content=f"🔹 **--- ХОД ОТРЯДА ---** 🔹{debuff_notes}\n🛑 **Ход игрока <@{player['id']}> ({player['class']}).** Ваш черед на передовой! Выберите навык:",
                attachments=[img_file], view=view
            )
            await view.wait()
            chosen_skill = view.chosen_skill

        damage = 0
        action_text = ""
        slow_applied = False
        
        if chosen_skill is None:
            action_text = f"пропустил свой ход! 💤"
        else:
            skill_name = chosen_skill["name"]
            base_damage = chosen_skill["damage"]
            dmg_type = chosen_skill.get("dmg_type", "none")
            heal_amount = chosen_skill["heal"]
            b_atk_pct = chosen_skill.get("buff_atk_pct", 0.0)
            b_def_pct = chosen_skill.get("buff_def_pct", 0.0)
            b_turns = chosen_skill.get("buff_turns", 0)
            skill_debuff = chosen_skill.get("debuff", None)
            
            action_text = f"использует **{skill_name}**"
            
            atk_mod = 1.0
            if session.atk_buff_turns > 0: atk_mod += session.atk_buff_value
            for d in player.get("debuffs", []):
                if d["type"] == "ослабление атаки": atk_mod -= d.get("power_pct", 0.0)
            
            if base_damage > 0:
                base_damage = int(base_damage * max(0.1, atk_mod))
                if dmg_type == "physical": damage = max(1, int(base_damage * (1 - session.boss_phys_def)))
                elif dmg_type == "magical": damage = max(1, int(base_damage * (1 - session.boss_mag_def)))
                else: damage = base_damage
            
            if heal_amount > 0:
                action_text += f" (+{heal_amount} HP команде!)"
                for p in session.players.values():
                    if p["is_alive"]: p["hp"] = min(100, p["hp"] + heal_amount)

            if b_turns > 0:
                if b_atk_pct > 0:
                    session.atk_buff_value = b_atk_pct
                    session.atk_buff_turns = b_turns
                if b_def_pct > 0:
                    session.def_buff_value = b_def_pct
                    session.def_buff_turns = b_turns

            # === 🎯 НАКЛАДЫВАНИЕ ДЕБАФФОВ НА БОССА ===
            if skill_debuff:
                db_type = skill_debuff["type"]
                
                if db_type == "замедление":
                    if session.boss_slow_stacks >= 2:
                        action_text += f"\n❌ **ИММУНИТЕТ!** Босс адаптировался к магии льда, [Замедление] больше не действует!"
                    else:
                        session.boss_slow_stacks += 1
                        slow_applied = True
                        session.boss_debuffs.append({
                            "type": db_type,
                            "duration": skill_debuff["duration"],
                            "power_pct": skill_debuff.get("power_pct", 0.0)
                        })
                        action_text += f"\n❄️ **ЗАМЕДЛЕНИЕ!** Атака босса отложена на 1 ход! (Сопротивление босса: {session.boss_slow_stacks}/2)"
                else:
                    session.boss_debuffs.append({
                        "type": db_type,
                        "damage": skill_debuff.get("damage", 0),
                        "duration": skill_debuff["duration"],
                        "power_pct": skill_debuff.get("power_pct", 0.0)
                    })
                    action_text += f"\n💥 На босса наложен эффект: **{db_type}** ({skill_debuff['duration']}т)"

        session.boss_hp = max(0, session.boss_hp - damage)
        
        if session.atk_buff_turns > 0: session.atk_buff_turns -= 1
        if session.def_buff_turns > 0: session.def_buff_turns -= 1
        
        # Тики дотов на боссе
        boss_tick_damage = 0
        boss_tick_notes = ""
        for d in list(session.boss_debuffs):
            if d["type"] in ["горение", "отравление"]:
                boss_tick_damage += d.get("damage", 0)
                boss_tick_notes += f"\n🔥 Босс теряет **{d.get('damage', 0)}** HP от эффекта [{d['type']}]."
            d["duration"] -= 1
            if d["duration"] <= 0:
                session.boss_debuffs.remove(d)
                if d["type"] == "замедление":
                    session.boss_slow_stacks = 0
                    boss_tick_notes += f"\n✨ Эффект замедления спал. Босс сбросил сопротивление льду!"
                else:
                    boss_tick_notes += f"\n✨ Эффект [{d['type']}] на боссе рассеялся."
                
        session.boss_hp = max(0, session.boss_hp - boss_tick_damage)

        # === 🔄 СЧЕТЧИК ХОДОВ БОССА С ДИНАМИЧЕСКИМ УСКОРЕНИЕМ (ЯРОСТЬ) ===
        current_alive_count = len([p for p in session.players.values() if p["is_alive"]])
        
        if current_alive_count >= 5: max_boss_cooldown = 3
        elif current_alive_count >= 3: max_boss_cooldown = 2
        else: max_boss_cooldown = 1
        
        if slow_applied:
            boss_cooldown_notice = "\n⏳ Счетчик атаки босса замерз из-за замедления!"
            boss_trigger = False
        else:
            session.boss_cooldown_counter += 1
            boss_cooldown_notice = f"\n⏳ Зарядка атаки босса: {session.boss_cooldown_counter}/{max_boss_cooldown}"
            
            if session.boss_cooldown_counter >= max_boss_cooldown:
                boss_trigger = True
                session.boss_cooldown_counter = 0
            else:
                boss_trigger = False

        # Походивший отправляется в конец очереди
        session.turn_order.append(session.turn_order.pop(0))
        
        img_file = generate_battle_image(current_player_id=None, boss_action_ready=boss_trigger)
        display_mention = player['name'] if player.get("is_npc") else f"<@{player['id']}>"
        
        tick_msg_text = f"\n🔥 Босс получает **{boss_tick_damage}** периодического урона." if boss_tick_damage > 0 else ""
        await battle_message.edit(
            content=f"⚔️ {display_mention} {action_text} и наносит **{damage}** урона!{tick_msg_text}{boss_tick_notes}{boss_cooldown_notice} (У босса: {session.boss_hp} HP)",
            attachments=[img_file], view=None
        )
        await asyncio.sleep(5.0)

        if session.boss_hp <= 0:
            break

        # ================= 👹 ДИНАМИЧЕСКИЙ ХОД БОССА =================
        if boss_trigger:
            alive_players = [p for p in session.players.values() if p["is_alive"]]
            if not alive_players:
                break
                
            boss_atk = random.choice(session.boss_attacks)
            targets_to_hit = alive_players if boss_atk["target"] == "aoe" else [random.choice(alive_players)]
            
            if boss_atk["target"] == "aoe":
                boss_atk_text = f"👹 **{session.boss_name}** накопил ярость и проводит **AOE атаку: {boss_atk['name']}** по всему отряду!"
            else:
                t_mention = targets_to_hit[0]['name'] if targets_to_hit[0].get("is_npc") else f"<@{targets_to_hit[0]['id']}>"
                boss_atk_text = f"👹 **{session.boss_name}** обрушивает накопленную мощь на {t_mention} атакой **{boss_atk['name']}**!"

            death_reports = ""
            for target in targets_to_hit:
                base_boss_dmg = random.randint(boss_atk["min_damage"], boss_atk["max_damage"])
                
                # Ослабление атаки босса
                boss_atk_mod = 1.0
                for d in session.boss_debuffs:
                    if d["type"] == "ослабление атаки": 
                        boss_atk_mod -= d.get("power_pct", 0.0)
                base_boss_dmg = int(base_boss_dmg * max(0.1, boss_atk_mod))

                # Снижение щитом команды
                if session.def_buff_turns > 0:
                    boss_damage = max(1, int(base_boss_dmg * (1 - session.def_buff_value)))
                else:
                    boss_damage = base_boss_dmg
                    
                target["hp"] = max(0, target["hp"] - boss_damage)
                
                if boss_atk.get("effect") and target["hp"] > 0:
                    target["debuffs"].append({
                        "type": boss_atk["effect"]["type"],
                        "damage": boss_atk["effect"].get("damage", 0),
                        "duration": boss_atk["effect"]["duration"],
                        "power_pct": boss_atk["effect"].get("power_pct", 0.0)
                    })
                
                t_mention = target['name'] if target.get("is_npc") else f"<@{target['id']}>"
                boss_atk_text += f"\n💥 {t_mention} получает **{boss_damage}** урона."
                if boss_atk.get("effect"):
                    boss_atk_text += f" ☣️ Наложен дебафф: **{boss_atk['effect']['type']}**"

                if target["hp"] <= 0:
                    target["is_alive"] = False
                    death_reports += f"\n💀 {t_mention} погиб в бою и покидает отряд!"
                    if target["id"] in session.turn_order:
                        session.turn_order.remove(target["id"])

            img_file = generate_battle_image(current_player_id=None, boss_action_ready=False)
            await battle_message.edit(content=f"{boss_atk_text}{death_reports}", attachments=[img_file], view=None)
            await asyncio.sleep(5.0)
            round_number += 1

    # === ФИНАЛ БИТВЫ ===
    img_file = generate_battle_image()
    if session.boss_hp <= 0:
        await battle_message.edit(content=f"🎉 **ПОБЕДА!** **{session.boss_name}** повержен! Отряд празднует триумф! 🏆", attachments=[img_file], view=None)
    else:
        await battle_message.edit(content=f"💀 **ПОРАЖЕНИЕ...** Отряд полностью уничтожен. **{session.boss_name}** победил. 👹", attachments=[img_file], view=None)

    session.state = "IDLE"

@bot.command(name="присоединиться", aliases=["join"])
async def join_game(ctx, role: str = None):
    """Команда для вступления в битву"""
    global session, AVAILABLE_CLASSES
    if session.state == "IDLE":
        await ctx.send("💤 Сейчас нет активного босса. Напишите `!старт`.")
        return
    if session.state == "BATTLING":
        await ctx.send("⚔️ Битва уже началась, вы опоздали!")
        return
    if not role or role.lower() not in AVAILABLE_CLASSES:
        await ctx.send(f"❌ Доступные классы: {', '.join(AVAILABLE_CLASSES)}")
        return

    role = role.lower()
    user = ctx.author
    if str(user.id) in session.players:
        await ctx.send(f"⚠️ Вы уже в строю!")
        return

    session.players[str(user.id)] = {
        "id": user.id,
        "name": user.display_name,
        "class": role,
        "hp": 100,
        "is_alive": True,
        "is_npc": False,
        "debuffs": []
    }
    await ctx.send(f"✅ {user.mention} готов к бою как **{role}**!")

bot.run(os.getenv('DISCORD_TOKEN'))