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

# Глобальная переменная для хранения главного сообщения битвы
battle_message = None

def load_game_data():
    with open("skills.json", "r", encoding="utf-8") as f:
        skills_data = json.load(f)
    with open("bosses.json", "r", encoding="utf-8") as f:
        bosses_data = json.load(f)
    return skills_data, bosses_data

# Загружаем конфигурацию игры
CLASS_SKILLS, BOSSES_LIST = load_game_data()
AVAILABLE_CLASSES = list(CLASS_SKILLS.keys())

class GameSession:
    def __init__(self):
        self.state = "IDLE"
        self.players = {}
        self.boss_name = ""
        self.boss_hp = 0
        self.boss_max_hp = 0
        self.boss_min_dmg = 0
        self.boss_max_dmg = 0
        self.turn_order = []
        self.current_turn_index = 0

session = GameSession()

# === 🎉 ФУНКЦИЯ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЯ БИТВЫ ===
def generate_battle_image(current_player_id=None):
    # 1. Открываем фоновое изображение
    try:
        bg = Image.open("assets/background.png").convert("RGBA")
    except FileNotFoundError:
        bg = Image.new("RGBA", (800, 400), (40, 40, 40, 255))
        
    draw = ImageDraw.Draw(bg)
    
    # 2. Загружаем шрифт Linux с поддержкой русского языка (DejaVu)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font_name = ImageFont.truetype(font_path, 14)  # Для ников и имени босса
        font_hp = ImageFont.truetype(font_path, 11)    # Для цифр внутри полосок ХП
    except IOError:
        font_name = ImageFont.load_default()
        font_hp = ImageFont.load_default()

    # 3. ОТРИСОВКА БОССА
    boss_w, boss_h = 200, 200  # Компактный размер босса
    boss_x, boss_y = 40, 160   # Позиция на левой части тропинки
    
    try:
        boss_img = Image.open("assets/boss.png").convert("RGBA")
        boss_img = boss_img.resize((boss_w, boss_h), Image.Resampling.NEAREST)
        bg.paste(boss_img, (boss_x, boss_y), boss_img)
    except FileNotFoundError:
        draw.rectangle([boss_x, boss_y, boss_x + boss_w, boss_y + boss_h], fill=(200, 50, 50, 255))
    
    # Полоска ХП Босса над его головой
    draw.text((boss_x, boss_y - 40), f"{session.boss_name}", fill="white", font=font_name)
    draw.rectangle([boss_x, boss_y - 20, boss_x + boss_w, boss_y - 10], fill=(60, 20, 20)) # Задник
    
    hp_percent = session.boss_hp / session.boss_max_hp
    draw.rectangle([boss_x, boss_y - 20, boss_x + int(boss_w * hp_percent), boss_y - 10], fill=(220, 40, 40)) # Красная шкала
    draw.text((boss_x + 5, boss_y - 21), f"{session.boss_hp} / {session.boss_max_hp}", fill="white", font=font_hp)

    # 4. ОТРИСОВКА ИГРОКОВ
    p_w, p_h = 80, 80      # Размер картинок персонажей
    start_x = 420          # Начало строя
    spacing_x = 90         # Расстояние между игроками в ряду
    base_y = 240           # Опустили игроков на тропинку
    
    for idx, p_id in enumerate(session.turn_order):
        player = session.players[p_id]
        if not player["is_alive"]:
            continue
            
        is_his_turn = (p_id == current_player_id)
        
        x = start_x + (idx * spacing_x)
        y = base_y
        
        # Эффект шага вперед: активный игрок выдвигается влево к боссу и чуть вниз
        if is_his_turn:
            x -= 40  
            y += 15  
            
        try:
            p_img = Image.open(f"assets/{player['class']}.png").convert("RGBA")
            p_img = p_img.resize((p_w, p_h), Image.Resampling.NEAREST)
            bg.paste(p_img, (x, y), p_img)
        except FileNotFoundError:
            color = (80, 80, 220) if player['class'] == 'бард' else (220, 180, 60)
            draw.rectangle([x, y, x + p_w, y + p_h], fill=color)

        # Никнейм над головой игрока
        display_name = player["user"].display_name[:12]
        name_color = "#FFD700" if is_his_turn else "white"  # Золотой цвет во время своего хода
        draw.text((x, y - 35), display_name, fill=name_color, font=font_name)
        
        # Полоска ХП над головой игрока (выровнена ровно по ширине персонажа `p_w`)
        draw.rectangle([x, y - 15, x + p_w, y - 8], fill=(60, 20, 20))
        p_hp_percent = player["hp"] / 100
        draw.rectangle([x, y - 15, x + int(p_w * p_hp_percent), y - 8], fill=(40, 220, 40)) # Зеленая шкала

    # Сохраняем изображение в буфер памяти
    img_byte_arr = io.BytesIO()
    bg.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return discord.File(fp=img_byte_arr, filename="battle.png")


# === ПАНЕЛЬ КНОПОК ДЛЯ ХОДА ИГРОКА ===
class TurnButtons(discord.ui.View):
    def __init__(self, player, timeout=30):
        super().__init__(timeout=timeout)
        self.player = player
        self.chosen_skill = None
        
        player_class = player["class"]
        skills = CLASS_SKILLS.get(player_class, [])
        
        for skill in skills:
            button = discord.ui.Button(
                label=skill["name"], 
                custom_id=skill["id"], 
                style=discord.ButtonStyle.primary
            )
            button.callback = self.make_callback(skill)
            self.add_item(button)

    def make_callback(self, skill):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player["user"].id:
                await interaction.response.send_message("❌ Сейчас не ваш ход!", ephemeral=True)
                return
                
            self.chosen_skill = skill
            for item in self.children:
                item.disabled = True
                
            await interaction.response.defer()
            self.stop()
            
        return callback

    async def on_timeout(self):
        self.stop()

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} успешно запущен и готов обрабатывать JSON!')

@bot.command(name="старт")
async def start_boss(ctx):
    """Команда для запуска лобби и проведения пошагового боя с картинкой"""
    global session, BOSSES_LIST, CLASS_SKILLS, battle_message
    
    # Обновляем данные на лету
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
    session.boss_min_dmg = current_boss["min_damage"]
    session.boss_max_dmg = current_boss["max_damage"]
    
    await ctx.send(
        f"🚨 **ВНИМАНИЕ! Появился босс: {session.boss_name} [❤️ {session.boss_hp} HP]!** 🚨\n"
        f"У вас есть 30 секунд, чтобы присоединиться!\n"
        f"Пишите: `!присоединиться [класс]`"
    )

    await asyncio.sleep(30)

    if len(session.players) == 0:
        session.state = "IDLE"
        await ctx.send(f"😔 Никто не пришел на битву.")
        return

    session.state = "BATTLING"
    
    # Генерируем случайную очередь ходов игроков
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

        # 1. ПОШАГОВЫЙ ХОД ИГРОКОВ
        for p_id in session.turn_order:
            player = session.players[p_id]
            if not player["is_alive"]:
                continue
                
            img_file = generate_battle_image(current_player_id=p_id)
            view = TurnButtons(player, timeout=30)
            
            await battle_message.edit(
                content=f"🔹 **РАУНД {round_number}** 🔹\n🛑 **Ход игрока {player['user'].mention} ({player['class']}).** Выберите навык:",
                attachments=[img_file], 
                view=view
            )
            
            await view.wait()
            
            damage = 0
            action_text = ""
            
            if view.chosen_skill is None:
                action_text = "пропустил свой ход! 💤"
            else:
                skill_id = view.chosen_skill["id"]
                
                # Хэндлеры навыков
                if skill_id == "warrior_slash":
                    damage = 25
                    action_text = "использует **⚔️ Сильный удар**"
                elif skill_id == "warrior_shield":
                    damage = 10
                    action_text = "использует **🛡️ Глухую оборону**"
                elif skill_id == "warrior_execute":
                    damage = random.randint(10, 40)
                    action_text = "проводит **💥 Казнь**"
                elif skill_id == "mage_fireball":
                    damage = 35
                    action_text = "выпускает **🔥 Огненный шар**"
                elif skill_id == "mage_ice":
                    damage = 20
                    action_text = "кастует **❄️ Ледяную стрелу**"
                elif skill_id == "mage_lightning":
                    damage = 45
                    action_text = "обрушивает **⚡ Грозу**"
                elif skill_id == "bard_heal":
                    damage = 5
                    action_text = "поет **🎵 Песню исцеления** (+15 HP команде)!"
                    for p in session.players.values():
                        if p["is_alive"]:
                            p["hp"] = min(100, p["hp"] + 15)
                elif skill_id == "bard_solo":
                    damage = 20
                    action_text = "играет **🎸 Соло на лютне**"
                elif skill_id == "bard_buff":
                    damage = 15
                    action_text = "заводит **✨ Боевой марш**"

            session.boss_hp = max(0, session.boss_hp - damage)
            
            img_file = generate_battle_image(current_player_id=p_id)
            await battle_message.edit(
                content=f"⚔️ {player['user'].mention} {action_text} и наносит **{damage}** урона! (У босса осталось: {session.boss_hp} HP)", 
                attachments=[img_file],
                view=None
            )
            await asyncio.sleep(2.5)

            if session.boss_hp <= 0:
                break

        if session.boss_hp <= 0:
            break

        # 2. ХОД БОССА
        alive_players = [p for p in session.players.values() if p["is_alive"]]
        target = random.choice(alive_players)
        
        boss_damage = random.randint(session.boss_min_dmg, session.boss_max_dmg)
        target["hp"] -= boss_damage
        
        death_text = ""
        if target["hp"] <= 0:
            target["hp"] = 0
            target["is_alive"] = False
            death_text = f"\n💀 {target['user'].mention} погиб в бою!"

        img_file = generate_battle_image(current_player_id=None)
        await battle_message.edit(
            content=f"👹 **Ход Босса!**\n{session.boss_name} яростно бьет {target['user'].mention} на **{boss_damage}** урона!{death_text}",
            attachments=[img_file],
            view=None
        )
        
        await asyncio.sleep(3)
        round_number += 1

    # === ФИНАЛ БИТВЫ ===
    img_file = generate_battle_image()
    if session.boss_hp <= 0:
        await battle_message.edit(content=f"🎉 **ПОБЕДА!** **{session.boss_name}** повержен! Игроки победили! 🏆", attachments=[img_file], view=None)
    else:
        await battle_message.edit(content=f"💀 **ПОРАЖЕНИЕ...** Все игроки были уничтожены. **{session.boss_name}** победил. 👹", attachments=[img_file], view=None)

    session.state = "IDLE"

@bot.command(name="присоединиться", aliases=["join"])
async def join_game(ctx, role: str = None):
    """Команда для вступления в битву"""
    global session, AVAILABLE_CLASSES
    
    if session.state == "IDLE":
        await ctx.send("💤 Сейчас нет активного босса. Напишите `!старт`, чтобы призвать его.")
        return
    if session.state == "BATTLING":
        await ctx.send("⚔️ Битва уже началась, вы опоздали!")
        return

    if not role or role.lower() not in AVAILABLE_CLASSES:
        await ctx.send(f"❌ Доступные классы: {', '.join(AVAILABLE_CLASSES)}\nПример: `!присоединиться бард`")
        return

    role = role.lower()
    user = ctx.author

    if user.id in session.players:
        await ctx.send(f"⚠️ {user.mention}, вы уже в строю как **{session.players[user.id]['class']}**!")
        return

    session.players[user.id] = {
        "user": user,
        "class": role,
        "hp": 100,
        "is_alive": True
    }
    
    await ctx.send(f"✅ {user.mention} присоединился к рейду в роли **{role}**!")

bot.run(os.getenv('DISCORD_TOKEN'))