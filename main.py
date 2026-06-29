import discord
from discord.ext import commands
import asyncio
import random
import os
from dotenv import load_dotenv

# Загружаем токен из скрытого файла .env
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

AVAILABLE_CLASSES = ["бард", "воин", "маг"]

# Данные о навыках для каждого класса
CLASS_SKILLS = {
    "воин": [
        {"name": "⚔️ Сильный удар", "id": "warrior_slash", "desc": "Наносит 25 урона"},
        {"name": "🛡️ Глухая оборона", "id": "warrior_shield", "desc": "Защищает и наносит 10 урона"},
        {"name": "💥 Казнь", "id": "warrior_execute", "desc": "Рискованный удар: от 10 до 40 урона"}
    ],
    "маг": [
        {"name": "🔥 Огненный шар", "id": "mage_fireball", "desc": "Наносит 35 урона"},
        {"name": "❄️ Ледяная стрела", "id": "mage_ice", "desc": "Наносит 20 урона"},
        {"name": "⚡ Гроза", "id": "mage_lightning", "desc": "Мощная магия: 45 урона"}
    ],
    "бард": [
        {"name": "🎵 Песня исцеления", "id": "bard_heal", "desc": "Лечит ВСЮ команду на 15 HP, урон 5"},
        {"name": "🎸 Соло на лютне", "id": "bard_solo", "desc": "Наносит 20 урона"},
        {"name": "✨ Боевой марш", "id": "bard_buff", "desc": "Оглушает босса звуком: 15 урона"}
    ]
}

class GameSession:
    def __init__(self):
        self.state = "IDLE"
        self.players = {}
        self.boss_hp = 600  # Немного увеличим ХП босса, так как навыки стали сильнее
        self.boss_name = "Орк-Разрушитель"

session = GameSession()

# === ПАНЕЛЬ КНОПОК ДЛЯ ХОДА ИГРОКА ===
class TurnButtons(discord.ui.View):
    def __init__(self, player, timeout=30):
        super().__init__(timeout=timeout)
        self.player = player
        self.chosen_skill = None  # Сюда запишется выбранный навык
        
        # Динамически создаем кнопки на основе класса игрока
        player_class = player["class"]
        skills = CLASS_SKILLS[player_class]
        
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
            # Проверяем, что на кнопку нажал именно тот игрок, чья сейчас очередь
            if interaction.user.id != self.player["user"].id:
                await interaction.response.send_message("❌ Сейчас не ваш ход!", ephemeral=True)
                return
                
            self.chosen_skill = skill
            # Отключаем кнопки после нажатия, чтобы нельзя было кликнуть дважды
            for item in self.children:
                item.disabled = True
                
            await interaction.response.edit_message(view=self)
            self.stop() # Останавливаем ожидание view
            
        return callback

    async def on_timeout(self):
        # Если игрок АФК и не нажал кнопку за 30 секунд
        self.stop()

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} успешно запущен и готов к пошаговому бою!')

@bot.command(name="старт")
async def start_boss(ctx):
    """Команда для запуска лобби на босса и проведения пошагового боя"""
    global session
    
    if session.state != "IDLE":
        await ctx.send("⚠️ Битва или сбор уже идут!")
        return

    session.state = "RECRUITING"
    session.players.clear()
    session.boss_hp = 600
    
    await ctx.send(
        f"🚨 **ВНИМАНИЕ! Появился босс: {session.boss_name} [❤️ {session.boss_hp} HP]!** 🚨\n"
        f"У вас есть 30 секунд, чтобы присоединиться!\n"
        f"Пишите: `!присоединиться [бард/воин/маг]`"
    )

    await asyncio.sleep(30)

    if len(session.players) == 0:
        session.state = "IDLE"
        await ctx.send("😔 Никто не пришел на битву. Босс ушел.")
        return

    session.state = "BATTLING"
    await ctx.send(f"⚔️ **Время вышло! Битва начинается!** Участвуют бойцов: {len(session.players)}.")
    await asyncio.sleep(2)

    # === НАЧАЛО БОЕВОГО ЦИКЛА ===
    round_number = 1
    while session.boss_hp > 0:
        alive_players = [p for p in session.players.values() if p["is_alive"]]
        if not alive_players:
            break

        await ctx.send(f"🔹 **--- РАУНД {round_number} ---** 🔹")
        
        # 1. ПОШАГОВЫЙ ХОД ИГРОКОВ
        for p_id, player in session.players.items():
            if not player["is_alive"]:
                continue
                
            # Создаем и отправляем панель с кнопками навыков для текущего игрока
            view = TurnButtons(player, timeout=30)
            turn_msg = await ctx.send(
                f"🛑 **Ход игрока {player['user'].mention} ({player['class']}).** У вас {player['hp']}/100 HP.\n"
                f"Выберите ваш навык (нажатие на кнопку ниже):", 
                view=view
            )
            
            # Ждем, пока игрок нажмет кнопку или выйдет таймаут (30 сек)
            await view.wait()
            
            damage = 0
            action_text = ""
            
            if view.chosen_skill is None:
                # Если игрок ничего не выбрал (пропустил ход по таймауту)
                action_text = "пропустил свой ход из-за нерешительности! 💤"
            else:
                skill_id = view.chosen_skill["id"]
                
                # --- ЛОГИКА НАВЫКОВ ---
                # Воин
                if skill_id == "warrior_slash":
                    damage = 25
                    action_text = "использует **⚔️ Сильный удар**"
                elif skill_id == "warrior_shield":
                    damage = 10
                    action_text = "прикрывается щитом и использует **🛡️ Глухуя оборону**"
                elif skill_id == "warrior_execute":
                    damage = random.randint(10, 40)
                    action_text = f"рискует и проводит **💥 Казнь**"
                
                # Маг
                elif skill_id == "mage_fireball":
                    damage = 35
                    action_text = "выпускает во врага **🔥 Огненный шар**"
                elif skill_id == "mage_ice":
                    damage = 20
                    action_text = "замораживает босса с помощью **❄️ Ледяной стрелы**"
                elif skill_id == "mage_lightning":
                    damage = 45
                    action_text = "обрушивает с небес разрушительную **⚡ Грозу**"
                
                # Бард
                elif skill_id == "bard_heal":
                    damage = 5
                    action_text = "начинает играть **🎵 Песню исцеления**, восстанавливая всей команде по 15 HP!"
                    for p in session.players.values():
                        if p["is_alive"]:
                            p["hp"] = min(100, p["hp"] + 15)
                elif skill_id == "bard_solo":
                    damage = 20
                    action_text = "выдает драйвовое **🎸 Соло на лютне**"
                elif skill_id == "bard_buff":
                    damage = 15
                    action_text = "заводит вдохновляющий **✨ Боевой марш**"

            # Рассчитываем урон боссу
            session.boss_hp = max(0, session.boss_hp - damage)
            
            # Обновляем сообщение хода, убирая кнопки и заменяя текст на результат
            await turn_msg.edit(content=f"⚔️ {player['user'].mention} {action_text} и наносит **{damage}** урона! (У босса осталось: {session.boss_hp} HP)", view=None)
            await asyncio.sleep(2)

            if session.boss_hp <= 0:
                break

        if session.boss_hp <= 0:
            break

        # 2. ХОД БОССА
        alive_players = [p for p in session.players.values() if p["is_alive"]]
        target = random.choice(alive_players)
        
        boss_damage = random.randint(25, 45)
        target["hp"] -= boss_damage
        
        await ctx.send(f"👹 **{session.boss_name}** яростно атакует {target['user'].mention} и наносит **{boss_damage}** урона!")
        
        if target["hp"] <= 0:
            target["hp"] = 0
            target["is_alive"] = False
            await ctx.send(f"💀 {target['user'].mention} погиб в бою и теряет возможность участвовать!")
        else:
            await ctx.send(f"❤️ У {target['user'].mention} осталось {target['hp']}/100 HP.")
            
        await asyncio.sleep(3)
        round_number += 1

    # === ФИНАЛ БИТВЫ ===
    if session.boss_hp <= 0:
        await ctx.send(f"🎉 **ПОБЕДА!** **{session.boss_name}** повержен! Игроки победили! 🏆")
    else:
        await ctx.send(f"💀 **ПОРАЖЕНИЕ...** Все игроки были уничтожены. **{session.boss_name}** победил. 👹")

    session.state = "IDLE"

@bot.command(name="присоединиться", aliases=["join"])
async def join_game(ctx, role: str = None):
    """Команда для вступления в битву"""
    global session
    
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