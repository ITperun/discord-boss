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
        self.boss_phys_def = 0.0
        self.boss_mag_def = 0.0
        
        self.turn_order = []
        
        # СИСТЕМА КОМАНДНЫХ БАФФОВ
        self.atk_buff_value = 0.0   
        self.atk_buff_turns = 0     
        
        self.def_buff_value = 0.0   
        self.def_buff_turns = 0     

session = GameSession()

# === 🎉 ОБНОВЛЕННАЯ ФУНКЦИЯ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЯ БИТВЫ ===
def generate_battle_image(current_player_id=None):
    try:
        bg = Image.open("assets/background.png").convert("RGBA")
    except FileNotFoundError:
        bg = Image.new("RGBA", (800, 400), (40, 40, 40, 255))
        
    draw = ImageDraw.Draw(bg)
    
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font_name = ImageFont.truetype(font_path, 12) # Немного уменьшили для идеальной посадки текста
        font_hp = ImageFont.truetype(font_path, 10)
    except IOError:
        font_name = ImageFont.load_default()
        font_hp = ImageFont.load_default()

    # Отрисовка босса
    boss_w, boss_h = 200, 200
    boss_x, boss_y = 40, 160
    
    try:
        boss_img = Image.open("assets/boss.png").convert("RGBA")
        boss_img = boss_img.resize((boss_w, boss_h), Image.Resampling.NEAREST)
        bg.paste(boss_img, (boss_x, boss_y), boss_img)
    except FileNotFoundError:
        draw.rectangle([boss_x, boss_y, boss_x + boss_w, boss_y + boss_h], fill=(200, 50, 50, 255))
    
    draw.text((boss_x, boss_y - 40), f"{session.boss_name} (🛡️Физ:{int(session.boss_phys_def*100)}% 🔮Маг:{int(session.boss_mag_def*100)}%)", fill="white", font=font_name)
    draw.rectangle([boss_x, boss_y - 20, boss_x + boss_w, boss_y - 10], fill=(60, 20, 20))
    
    hp_percent = session.boss_hp / session.boss_max_hp
    draw.rectangle([boss_x, boss_y - 20, boss_x + int(boss_w * hp_percent), boss_y - 10], fill=(220, 40, 40))
    draw.text((boss_x + 5, boss_y - 21), f"{session.boss_hp} / {session.boss_max_hp}", fill="white", font=font_hp)

    # Отображение баффов на экране
    buff_y = 20
    if session.atk_buff_turns > 0:
        draw.text((320, buff_y), f"⚔️ Бонус Атаки: +{int(session.atk_buff_value*100)}% ({session.atk_buff_turns} ходов)", fill="#FFD700", font=font_name)
        buff_y += 20
    if session.def_buff_turns > 0:
        draw.text((320, buff_y), f"🛡️ Защита команды: +{int(session.def_buff_value*100)}% ({session.def_buff_turns} ходов)", fill="#00FFFF", font=font_name)

    # 👥 ОТРИСОВКА ОТРЯДА
    p_w, p_h = 75, 75       
    start_x = 340           # Начальная позиция авангарда отряда
    spacing_x = 95          # 📊 УВЕЛИЧИЛИ РАССТОЯНИЕ, чтобы ники и полоски больше не сливались!
    base_y = 235           

    # Рисуем с конца очереди к началу, чтобы передние красиво перекрывали задних
    for idx, p_id in enumerate(reversed(session.turn_order)):
        player = session.players[p_id]
        if not player["is_alive"]:
            continue
            
        real_idx = len(session.turn_order) - 1 - idx
        is_his_turn = (p_id == current_player_id)
        
        # Координаты строя с учетом перспективы
        x = start_x + (real_idx * spacing_x)
        y = base_y - (real_idx * 6) # Чуть больше разводка по вертикали для объема

        if is_his_turn:
            x -= 30  
            y += 15  
            
        try:
            p_img = Image.open(f"assets/{player['class']}.png").convert("RGBA")
            p_img = p_img.resize((p_w, p_h), Image.Resampling.NEAREST)
            bg.paste(p_img, (x, y), p_img)
        except FileNotFoundError:
            color = (80, 80, 220) if player['class'] == 'бард' else (220, 180, 60)
            draw.rectangle([x, y, x + p_w, y + p_h], fill=color)

        display_name = player["name"][:10]
        name_color = "#FFD700" if is_his_turn else "white"
        
        # Ники и полоски отрисовываются строго над головой конкретного персонажа
        draw.text((x + 2, y - 35), display_name, fill=name_color, font=font_name)
        draw.rectangle([x, y - 15, x + p_w, y - 8], fill=(60, 20, 20))
        p_hp_percent = player["hp"] / 100
        draw.rectangle([x, y - 15, x + int(p_w * p_hp_percent), y - 8], fill=(40, 220, 40))

    img_byte_arr = io.BytesIO()
    bg.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return discord.File(fp=img_byte_arr, filename="battle.png")


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
            if str(interaction.user.id) != str(self.player["id"]):
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
    print(f'✅ Бот {bot.user} успешно запущен!')

@bot.command(name="старт")
async def start_boss(ctx):
    """Команда для запуска лобби и проведения пошагового боя"""
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
    session.boss_phys_def = current_boss.get("physical_def", 0.0)
    session.boss_mag_def = current_boss.get("magical_def", 0.0)
    
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

    # 👥 СНИЗИЛИ ЧИСЛО УЧАСТНИКОВ ДО 6 (Было 7)
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
                "is_npc": True
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

        # 1. ХОД АВАНГАРДА ОТРЯДА
        p_id = session.turn_order[0]
        player = session.players[p_id]
        
        # На всякий случай проверяем, жив ли первый (хотя мёртвых мы теперь удаляем сразу)
        if not player["is_alive"]:
            session.turn_order.append(session.turn_order.pop(0))
            continue
            
        img_file = generate_battle_image(current_player_id=p_id)
        chosen_skill = None
        
        if player.get("is_npc"):
            available_npc_skills = CLASS_SKILLS.get(player["class"], [])
            chosen_skill = random.choice(available_npc_skills)
            
            await battle_message.edit(
                content=f"🔹 **--- РАУНД {round_number} ---** 🔹\n🤖 **Ходит {player['name']} ({player['class']}).** Просчитывает тактику...",
                attachments=[img_file], 
                view=None
            )
            await asyncio.sleep(1.5)
        else:
            view = TurnButtons(player, timeout=30)
            await battle_message.edit(
                content=f"🔹 **--- РАУНД {round_number} ---** 🔹\n🛑 **Ход игрока <@{player['id']}> ({player['class']}).** Ваш черед на передовой! Выберите навык:",
                attachments=[img_file], 
                view=view
            )
            await view.wait()
            chosen_skill = view.chosen_skill

        damage = 0
        action_text = ""
        
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
            
            action_text = f"использует **{skill_name}**"
            
            if base_damage > 0:
                if session.atk_buff_turns > 0:
                    base_damage = int(base_damage * (1 + session.atk_buff_value))
                
                if dmg_type == "physical":
                    damage = max(1, int(base_damage * (1 - session.boss_phys_def)))
                    action_text += f" (Физический урон)"
                elif dmg_type == "magical":
                    damage = max(1, int(base_damage * (1 - session.boss_mag_def)))
                    action_text += f" (Магический урон)"
                else:
                    damage = base_damage
            
            if heal_amount > 0:
                action_text += f" (+{heal_amount} HP команде!)"
                for p in session.players.values():
                    if p["is_alive"]:
                        p["hp"] = min(100, p["hp"] + heal_amount)

            if b_turns > 0:
                if b_atk_pct > 0:
                    session.atk_buff_value = b_atk_pct
                    session.atk_buff_turns = b_turns
                    action_text += f"\n✨ Бафф: +{int(b_atk_pct*100)}% к атаке команды на {b_turns} ходов!"
                if b_def_pct > 0:
                    session.def_buff_value = b_def_pct
                    session.def_buff_turns = b_turns
                    action_text += f"\n🛡️ Щит: урон босса снижен на {int(b_def_pct*100)}% на {b_turns} ходов!"

        session.boss_hp = max(0, session.boss_hp - damage)
        
        if session.atk_buff_turns > 0:
            session.atk_buff_turns -= 1
        if session.def_buff_turns > 0:
            session.def_buff_turns -= 1
        
        # Переставляем ходившего в конец отряда
        session.turn_order.append(session.turn_order.pop(0))
        
        img_file = generate_battle_image(current_player_id=None)
        display_mention = player['name'] if player.get("is_npc") else f"<@{player['id']}>"
        await battle_message.edit(
            content=f"⚔️ {display_mention} {action_text} и наносит **{damage}** урона! (У босса осталось: {session.boss_hp} HP)", 
            attachments=[img_file],
            view=None
        )
        await asyncio.sleep(5.0)

        if session.boss_hp <= 0:
            break

        # 2. ХОД БОССА
        alive_players = [p for p in session.players.values() if p["is_alive"]]
        target = random.choice(alive_players)
        
        base_boss_damage = random.randint(session.boss_min_dmg, session.boss_max_dmg)
        
        if session.def_buff_turns > 0:
            boss_damage = max(1, int(base_boss_damage * (1 - session.def_buff_value)))
            buff_notice = f" (Снижено щитом на {int(session.def_buff_value*100)}%)"
        else:
            boss_damage = base_boss_damage
            buff_notice = ""
            
        target["hp"] -= boss_damage
        
        target_mention = target['name'] if target.get("is_npc") else f"<@{target['id']}>"
        death_text = ""
        if target["hp"] <= 0:
            target["hp"] = 0
            target["is_alive"] = False
            death_text = f"\n💀 {target_mention} погиб в бою и выбывает из строя!"
            
            # 🛑 РЕШЕНИЕ ПРОБЛЕМЫ ПУСТЫХ ОКОН: Полностью вычёркиваем погибшего из очереди ходов!
            if target["id"] in session.turn_order:
                session.turn_order.remove(target["id"])

        img_file = generate_battle_image(current_player_id=None)
        await battle_message.edit(
            content=f"👹 **Ход Босса!**\n{session.boss_name} яростно бьет {target_mention} на **{boss_damage}** урона!{buff_notice}{death_text}",
            attachments=[img_file],
            view=None
        )
        
        await asyncio.sleep(5.0)
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

    if str(user.id) in session.players:
        await ctx.send(f"⚠️ {user.mention}, вы уже в строю как **{session.players[str(user.id)]['class']}**!")
        return

    session.players[str(user.id)] = {
        "id": user.id,
        "name": user.display_name,
        "class": role,
        "hp": 100,
        "is_alive": True,
        "is_npc": False
    }
    
    await ctx.send(f"✅ {user.mention} присоединился к рейду в роли **{role}**!")

bot.run(os.getenv('DISCORD_TOKEN'))