import discord
from discord.ext import commands
import asyncio
import random
import os
import json
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont  # Импортируем библиотеки для рисования
import io

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Глобальная переменная для хранения ID главного сообщения битвы
battle_message = None

def load_game_data():
    with open("skills.json", "r", encoding="utf-8") as f:
        skills_data = json.load(f)
    with open("bosses.json", "r", encoding="utf-8") as f:
        bosses_data = json.load(f)
    return skills_data, bosses_data

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
        self.turn_order = []  # Очередь ходов игроков
        self.current_turn_index = 0

session = GameSession()

# === 🎉 ФУНКЦИЯ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЯ БИТВЫ ===
def generate_battle_image(current_player_id=None):
    # Открываем фоновое изображение
    try:
        bg = Image.open("assets/background.png").convert("RGBA")
    except FileNotFoundError:
        # Если графики нет, создаем временную заглушку (800x400)
        bg = Image.new("RGBA", (800, 400), (40, 40, 40, 255))
        
    draw = ImageDraw.Draw(bg)
    
    # Пытаемся загрузить шрифт для ников (если нет, берется дефолтный)
    try:
        font = ImageFont.truetype("Arial.ttf", 16)
    except IOError:
        font = ImageFont.load_default()

    # 1. Отрисовка Босса (слева)
    try:
        boss_img = Image.open("assets/boss.png").convert("RGBA")
        bg.paste(boss_img, (50, 150), boss_img)
    except FileNotFoundError:
        # Заглушка босса, если файла нет
        draw.rectangle([50, 150, 200, 300], fill=(200, 50, 50, 255))
    
    # Полоска ХП Босса сверху его головы
    draw.text((50, 110), f"{session.boss_name}", fill="white", font=font)
    draw.rectangle([50, 130, 200, 140], fill=(100, 0, 0)) # Задник ХП
    hp_percent = session.boss_hp / session.boss_max_hp
    draw.rectangle([50, 130, int(50 + 150 * hp_percent), 140], fill=(255, 0, 0)) # Красная полоска

    # 2. Отрисовка игроков (справа, выстраиваются в ряд)
    # Координаты начала строя игроков
    start_x = 450
    spacing_x = 80 # Расстояние между игроками в очереди
    
    for idx, p_id in enumerate(session.turn_order):
        player = session.players[p_id]
        if not player["is_alive"]:
            continue
            
        # Определяем позицию. Если это текущий ходящий игрок — выдвигаем его вперед (ближе к боссу)
        is_his_turn = (p_id == current_player_id)
        
        x = start_x + (idx * spacing_x)
        y = 150
        
        if is_his_turn:
            x -= 40 # Выдвигается влево, ближе к боссу
            y += 20 # Чуть смещается по вертикали для акцента
            
        # Загружаем иконку класса
        try:
            p_img = Image.open(f"assets/{player['class']}.png").convert("RGBA")
            bg.paste(p_img, (x, y), p_img)
        except FileNotFoundError:
            # Заглушка игрока
            color = (50, 200, 50) if player['class'] == 'воин' else (50, 50, 200)
            draw.rectangle([x, y, x+50, y+50], fill=color)

        # Подпись ника над игроком
        display_name = player["user"].display_name[:10] # Обрезаем слишком длинные ники
        
        # Если его ход — подсвечиваем ник желтым цветом
        name_color = "yellow" if is_his_turn else "white"
        draw.text((x, y - 40), display_name, fill=name_color, font=font)
        
        # Микро-полоска ХП над головой игрока
        draw.rectangle([x, int(y - 15), int(x + 50), int(y - 10)], fill=(100, 0, 0))
        p_hp_percent = player["hp"] / 100
        draw.rectangle([x, int(y - 15), int(x + 50 * p_hp_percent), int(y - 10)], fill=(0, 255, 0))

    # Храним изображение в буфере памяти, чтобы не засорять диск
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
                
            # Просто подтверждаем нажатие, сообщение обновим в основном цикле
            await interaction.response.defer()
            self.stop()
            
        return callback

    async def on_timeout(self):
        self.stop()

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} успешно запущен!')

@bot.command(name="старт")
async def start_boss(ctx):
    """Команда для запуска лобби и проведения пошагового боя с картинкой"""
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
    
    # Генерируем фиксированную очередь ходов игроков на эту битву
    session.turn_order = list(session.players.keys())
    random.shuffle(session.turn_order) # Перемешиваем для случайного порядка
    
    # Отправляем ПЕРВОЕ сообщение боя с картинкой-заставкой
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
                
            # Обновляем картинку: передаем ID игрока, чтобы он выдвинулся вперед!
            img_file = generate_battle_image(current_player_id=p_id)
            view = TurnButtons(player, timeout=30)
            
            # РЕДАКТИРУЕМ старое сообщение (меняем текст, картинку и прикрепляем новые кнопки)
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
                
                # Логика навыков
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
            
            # Сразу после хода убираем кнопки и пишем лог атаки (картинку тоже обновляем, так как у босса убавилось ХП)
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

        # Во время хода босса никто из игроков не выдвинут вперед (передаем None)
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