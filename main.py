import discord
from discord.ext import commands
import asyncio

# Настраиваем интенты (разрешения для бота читать чат)
intents = discord.Intents.default()
intents.message_content = True

# Инициализируем бота с префиксом "!"
bot = commands.Bot(command_prefix="!", intents=intents)

# Доступные классы
AVAILABLE_CLASSES = ["бард", "воин", "маг"]

# Класс для хранения текущей игровой сессии
class GameSession:
    def __init__(self):
        self.state = "IDLE" # Возможные состояния: IDLE, RECRUITING, BATTLING
        self.players = {}   # Словарь {user_id: {"user": discord.Member, "class": str, "hp": 100}}
        self.boss_hp = 500
        self.boss_name = "Орк-Разрушитель"

# Глобальная переменная для сессии (позже можно перенести в БД или кэш)
session = GameSession()

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} успешно запущен!')

@bot.command(name="старт")
async def start_boss(ctx):
    """Команда для запуска лобби на босса"""
    global session
    
    if session.state != "IDLE":
        await ctx.send("⚠️ Битва или сбор уже идут!")
        return

    session.state = "RECRUITING"
    session.players.clear()
    
    await ctx.send(
        f"🚨 **ВНИМАНИЕ! Появился босс: {session.boss_name}!** 🚨\n"
        f"У вас есть 30 секунд, чтобы присоединиться!\n"
        f"Пишите: `!присоединиться [бард/воин/маг]`"
    )

    # Ждем 30 секунд для сбора игроков
    await asyncio.sleep(30)

    # Проверяем, собрался ли кто-то
    if len(session.players) == 0:
        session.state = "IDLE"
        await ctx.send("😔 Никто не пришел на битву. Босс ушел, насмехаясь над вами.")
        return

    # Переводим игру в стадию боя
    session.state = "BATTLING"
    await ctx.send(f"⚔️ **Время вышло! Битва начинается!** Участвуют бойцов: {len(session.players)}.")
    
    # ТУТ БУДЕТ ВЫЗОВ ИГРОВОГО ЦИКЛА (БОЯ)

@bot.command(name="присоединиться", aliases=["join"])
async def join_game(ctx, role: str = None):
    """Команда для вступления в битву"""
    global session
    
    # Проверки состояния
    if session.state == "IDLE":
        await ctx.send("💤 Сейчас нет активного босса. Напишите `!старт`, чтобы призвать его.")
        return
    if session.state == "BATTLING":
        await ctx.send("⚔️ Битва уже началась, вы опоздали!")
        return

    # Проверка класса
    if not role or role.lower() not in AVAILABLE_CLASSES:
        await ctx.send(f"❌ Пожалуйста, выберите существующий класс. Доступные: {', '.join(AVAILABLE_CLASSES)}\nПример: `!присоединиться бард`")
        return

    role = role.lower()
    user = ctx.author

    # Проверка, не присоединился ли игрок уже
    if user.id in session.players:
        await ctx.send(f"⚠️ {user.mention}, вы уже в строю как **{session.players[user.id]['class']}**!")
        return

    # Добавляем игрока
    session.players[user.id] = {
        "user": user,
        "class": role,
        "hp": 100, # Позже сделаем разное ХП для разных классов
        "is_alive": True
    }
    
    await ctx.send(f"✅ {user.mention} присоединился к рейду в роли **{role}**!")

# Запуск бота (Сюда нужно вставить токен твоего бота от Discord Developer Portal)
# bot.run('MTM2MjEwMDU0NTUzOTY3NDE0Mg.G9xMfI.ltqkoyV2P8VEVCvtF29vzKRnEbKQYq3_n1JsKc')