
import discord
from discord.ext import commands
import asyncio
import random

# Настраиваем интенты (разрешения для бота читать чат)
intents = discord.Intents.default()
intents.message_content = True

# Инициализируем бота с префиксом "!"
bot = commands.Bot(command_prefix="!", intents=intents)

# Доступные классы игрового режима
AVAILABLE_CLASSES = ["бард", "воин", "маг"]

# Класс для хранения текущей игровой сессии
class GameSession:
    def __init__(self):
        self.state = "IDLE" # Возможные состояния: IDLE, RECRUITING, BATTLING
        self.players = {}   # Словарь {user_id: {"user": discord.Member, "class": str, "hp": 100, "is_alive": bool}}
        self.boss_hp = 500  # Текущее ХП босса
        self.boss_name = "Орк-Разрушитель"

# Глобальная переменная для сессии
session = GameSession()

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} успешно запущен и готов к бою!')

@bot.command(name="старт")
async def start_boss(ctx):
    """Команда для запуска лобби на босса и проведения боя"""
    global session
    
    if session.state != "IDLE":
        await ctx.send("⚠️ Битва или сбор уже идут!")
        return

    session.state = "RECRUITING"
    session.players.clear()
    session.boss_hp = 500  # Сбрасываем ХП босса перед новым боем
    
    await ctx.send(
        f"🚨 **ВНИМАНИЕ! Появился босс: {session.boss_name} [❤️ {session.boss_hp} HP]!** 🚨\n"
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
    await ctx.send(f"⚔️ **Время вышло! Битва начинается!** Участвуют бойцов: {len(session.players)}.\nПриготовьтесь...")
    await asyncio.sleep(2) # Небольшая пауза для драматизма

    # === НАЧАЛО БОЕВОГО ЦИКЛА ===
    round_number = 1
    while session.boss_hp > 0:
        # Проверяем, жив ли хоть кто-то из игроков
        alive_players = [p for p in session.players.values() if p["is_alive"]]
        if not alive_players:
            break # Если живых игроков нет, выходим из цикла (босс победил)

        await ctx.send(f"🔹 **--- РАУНД {round_number} ---** 🔹")
        
        # 1. ХОД ИГРОКОВ (Все живые игроки атакуют босса по очереди)
        for p_id, player in session.players.items():
            if not player["is_alive"]:
                continue
                
            # Базовые параметры навыков по умолчанию
            damage = 15
            skill_text = "атакует мечом"
            
            # Логика в зависимости от выбранного класса
            if player["class"] == "маг":
                damage = 30
                skill_text = "кастует 🔥 Огненный Шар"
            elif player["class"] == "бард":
                damage = 10
                skill_text = "играет на лютне 🎵 Боевой Марш (и лечит команду на 5 HP)"
                # Подлечим всех живых союзников в рейде
                for p in alive_players:
                    p["hp"] = min(100, p["hp"] + 5)
            elif player["class"] == "воин":
                damage = 20
                skill_text = "делает 💪 Мощный Удар"

            # Наносим урон боссу
            session.boss_hp -= damage
            if session.boss_hp < 0:
                session.boss_hp = 0

            await ctx.send(f"⚔️ Игрок {player['user'].mention} ({player['class']}) {skill_text} и наносит **{damage}** урона! (У босса осталось: {session.boss_hp} HP)")
            await asyncio.sleep(1.5) # Пауза между ходами игроков, чтобы чат не летел слишком быстро

            if session.boss_hp <= 0:
                break # Босс умер посреди раунда, прекращаем атаки остальных

        if session.boss_hp <= 0:
            break # Выходим из основного цикла, если босс повержен

        # 2. ХОД БОССА (Если он еще жив, он бьет случайного живого игрока)
        alive_players = [p for p in session.players.values() if p["is_alive"]] # Обновляем список выживших
        target = random.choice(alive_players)
        
        boss_damage = random.randint(25, 45) # Случайный урон босса за удар
        target["hp"] -= boss_damage
        
        await ctx.send(f"👹 **{session.boss_name}** яростно атакует {target['user'].mention} и наносит **{boss_damage}** урона!")
        
        # Проверяем, выжил ли игрок после атаки босса
        if target["hp"] <= 0:
            target["hp"] = 0
            target["is_alive"] = False
            await ctx.send(f"💀 {target['user'].mention} погиб в бою и выбывает из текущей битвы!")
        else:
            await ctx.send(f"❤️ У {target['user'].mention} осталось {target['hp']}/100 HP.")
            
        await asyncio.sleep(2) # Пауза перед следующим раундом
        round_number += 1

    # === ФИНАЛ БИТВЫ ===
    if session.boss_hp <= 0:
        await ctx.send(f"🎉 **ПОБЕДА!** **{session.boss_name}** повержен! Игроки празднуют победу в таверне! 🏆")
    else:
        await ctx.send(f"💀 **ПОРАЖЕНИЕ...** Все игроки были уничтожены. **{session.boss_name}** победоносно рычит над вашими телами. 👹")

    # Сбрасываем игру в исходное состояние для новых битв
    session.state = "IDLE"

@bot.command(name="присоединиться", aliases=["join"])
async def join_game(ctx, role: str = None):
    """Команда для вступления в битву"""
    global session
    
    # Проверки текущего состояния игры
    if session.state == "IDLE":
        await ctx.send("💤 Сейчас нет активного босса. Напишите `!старт`, чтобы призвать его.")
        return
    if session.state == "BATTLING":
        await ctx.send("⚔️ Битва уже началась, вы опоздали!")
        return

    # Проверка правильности ввода класса
    if not role or role.lower() not in AVAILABLE_CLASSES:
        await ctx.send(f"❌ Пожалуйста, выберите существующий класс. Доступные: {', '.join(AVAILABLE_CLASSES)}\nПример: `!присоединиться бард`")
        return

    role = role.lower()
    user = ctx.author

    # Проверка, не зашел ли игрок в лобби дважды
    if user.id in session.players:
        await ctx.send(f"⚠️ {user.mention}, вы уже в строю как **{session.players[user.id]['class']}**!")
        return

    # Добавляем игрока в сессию
    session.players[user.id] = {
        "user": user,
        "class": role,
        "hp": 100,
        "is_alive": True
    }
    
    await ctx.send(f"✅ {user.mention} присоединился к рейду в роли **{role}**!")

# Запуск бота с твоим токеном
bot.run('MTM2MjEwMDU0NTUzOTY3NDE0Mg.G9xMfI.ltqkoyV2P8VEVCvtF29vzKRnEbKQYq3_n1JsKc')