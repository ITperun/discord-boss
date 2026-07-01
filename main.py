import discord
from discord.ext import commands
import asyncio
import random
import os
from dotenv import load_dotenv

import config
from game_state import session
import database
from graphics import generate_battle_image, generate_profile_image, generate_endgame_image
from effects import generate_status_text
from combat import clean_dead_casters, execute_skill, process_global_tick, execute_boss_attack
from ui import TurnButtons, TargetView, ProfileView, ShopView

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

bot.remove_command('help')

# Глобальная переменная для хранения ID канала
ALLOWED_CHANNEL_ID = None

@bot.event
async def on_ready(): 
    print(f'✅ Бот {bot.user} запущен и модули загружены!')

# 🔥 ПРОВЕРКА КАНАЛА ДЛЯ ВСЕХ КОМАНД
@bot.check
async def restrict_channel(ctx):
    # Команду !канал можно использовать везде, чтобы иметь возможность перенастроить бота
    if ctx.command and ctx.command.name == "канал":
        return True
    # Если канал установлен, и мы находимся не в нем — игнорируем команду (True - разрешить, False - заблокировать)
    if ALLOWED_CHANNEL_ID is not None and ctx.channel.id != ALLOWED_CHANNEL_ID:
        return False
    return True

# === АДМИН-КОМАНДЫ ===
@bot.command(name="канал")
@commands.has_permissions(administrator=True)
async def set_channel(ctx, channel: discord.TextChannel = None):
    global ALLOWED_CHANNEL_ID
    if channel:
        ALLOWED_CHANNEL_ID = channel.id
        await ctx.send(f"✅ Бот привязан к каналу {channel.mention}. Команды в других чатах будут игнорироваться.")
    else:
        ALLOWED_CHANNEL_ID = None
        await ctx.send("✅ Привязка к каналу снята. Бот снова работает во всех чатах.")

@bot.command(name="выдать")
@commands.has_permissions(administrator=True)
async def give_item_or_gold(ctx, give_type: str, target: discord.Member, *, value: str):
    # Инициализируем профиль игрока на случай, если он еще ни разу не играл
    database.get_player(target.id, target.display_name)
    
    if give_type.lower() == "золото":
        try:
            amount = int(value)
            database.add_gold(target.id, amount)
            await ctx.send(f"💰 Игрок {target.mention} получил **{amount} золота** от администрации!")
        except ValueError:
            await ctx.send("❌ Ошибка: Укажите корректное число золота.")
            
    elif give_type.lower() == "предмет":
        config.reload_data()
        all_items = {**config.ITEMS_DB.get("weapons", {}), **config.ITEMS_DB.get("armor", {}), **config.ITEMS_DB.get("accessories", {})}
        
        found_id = None
        for k, v in all_items.items():
            # Проверяем совпадение как по ID (eng), так и по названию (рус)
            if k.lower() == value.lower() or v["name"].lower() == value.lower():
                found_id = k
                break
                
        if found_id:
            database.add_item(target.id, found_id)
            await ctx.send(f"🎁 Игрок {target.mention} получил **{all_items[found_id]['name']}** от администрации!")
        else:
            await ctx.send(f"❌ Ошибка: Предмет `{value}` не существует в базе.")
    else:
        await ctx.send("❌ Неизвестный тип. Используйте: `золото` или `предмет`.")

# Обработка ошибок админ-команд (если использует обычный игрок)
@set_channel.error
@give_item_or_gold.error
async def admin_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ У вас нет прав администратора для использования этой команды.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Неверный формат команды!\nИспользуйте: `!выдать золото @цель 100` или `!выдать предмет @цель Ржавый меч`")

# === ИГРОВЫЕ КОМАНДЫ ===
@bot.command(name="помощь", aliases=["help"])
async def show_help(ctx):
    text = (
        "📜 **Список доступных команд:**\n\n"
        "⚔️ `!старт` — Начать битву со случайным боссом.\n"
        "⚔️ `!старт [имя]` — Начать битву с конкретным боссом (например, `!старт некромант`).\n"
        "🛡️ `!присоединиться [класс]` / `!join` — Вступить в отряд. Классы: воин, маг, священник, бард, рейнджер, некромант.\n"
        "👤 `!профиль` — Показать свой профиль.\n"
        "🔍 `!профиль @пользователь` — Посмотреть профиль другого игрока.\n"
        "💰 `!кошелек` — Узнать количество золота.\n"
        "🛒 `!магазин` / `!shop` — Открыть магазин снаряжения.\n"
        "⚖️ `!продать [название]` / `!sell` — Продать предмет из инвентаря за 50% стоимости.\n"
        "❓ `!помощь` / `!help` — Показать это сообщение.\n\n"
        "👑 **Админ-команды:**\n"
        "• `!канал #канал` — Привязать бота к конкретному чату.\n"
        "• `!выдать золото @игрок число` — Выдать золото.\n"
        "• `!выдать предмет @игрок название` — Выдать предмет.\n"
    )
    await ctx.send(text)

@bot.command(name="кошелек")
async def check_wallet(ctx):
    player = database.get_player(ctx.author.id, ctx.author.display_name)
    await ctx.send(f"💰 {ctx.author.mention}, в твоем кошельке **{player['gold']} золота**.")

@bot.command(name="профиль")
async def show_profile(ctx, target: discord.Member = None):
    target_user = target if target else ctx.author
    is_own = (target_user == ctx.author)
    
    player_data = database.get_player(target_user.id, target_user.display_name)
    stats = database.get_total_stats(target_user.id)
    
    avatar_bytes = None
    try:
        avatar_bytes = await target_user.display_avatar.replace(size=256, format="png").read()
    except Exception:
        pass
        
    file = generate_profile_image(player_data, stats, avatar_bytes)
    
    if is_own:
        view = ProfileView(ctx.author.id)
        await ctx.send(file=file, view=view)
    else:
        await ctx.send(f"👤 Профиль игрока **{target_user.display_name}**:", file=file)

@bot.command(name="продать", aliases=["sell"])
async def sell_item(ctx, *, item_name: str):
    config.reload_data()
    player = database.get_player(ctx.author.id, ctx.author.display_name)
    inv = player.get("inventory", [])
    
    if not inv:
        return await ctx.send("❌ Ваш инвентарь пуст.")
        
    # Собираем все существующие в игре предметы
    all_items = {**config.ITEMS_DB.get("weapons", {}), **config.ITEMS_DB.get("armor", {}), **config.ITEMS_DB.get("accessories", {})}
    
    found_id = None
    # Ищем предмет в инвентаре игрока по названию (игнорируя регистр)
    for i_id in inv:
        item_data = all_items.get(i_id)
        if item_data and item_data["name"].lower() == item_name.lower():
            found_id = i_id
            break
            
    if not found_id:
        return await ctx.send(f"❌ У вас в инвентаре нет предмета `{item_name}`.")
        
    item_data = all_items[found_id]
    sell_price = item_data.get("price", 0) // 2
    
    if database.remove_item(ctx.author.id, found_id):
        database.add_gold(ctx.author.id, sell_price)
        await ctx.send(f"⚖️ Вы успешно продали **{item_data['name']}** за **{sell_price} золота**!")
    else:
        await ctx.send("❌ Произошла ошибка при продаже.")

# Обработчик ошибки, если игрок забыл написать название
@sell_item.error
async def sell_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Укажите название предмета! Например: `!продать Ржавый меч`")

@bot.command(name="магазин", aliases=["shop"])
async def show_shop(ctx):
    config.reload_data()
    view = ShopView(ctx.author.id)
    embed = view.generate_embed()
    await ctx.send(embed=embed, view=view)

@bot.command(name="старт")
async def start_boss(ctx, *, requested_boss: str = None):
    config.reload_data()
    
    if session.state != "IDLE": 
        return await ctx.send("⚠️ Битва уже идет!")

    if requested_boss:
        found_bosses = [b for b in config.BOSSES_LIST if requested_boss.lower() in b["name"].lower()]
        if not found_bosses:
            available = ", ".join([b["name"] for b in config.BOSSES_LIST])
            return await ctx.send(f"❌ Босс `{requested_boss}` не найден! Доступные боссы: {available}")
        boss = found_bosses[0]
    else:
        boss = random.choice(config.BOSSES_LIST)

    session.reset()
    session.state = "RECRUITING"
    session.boss_name, session.boss_hp, session.boss_max_hp = boss["name"], boss["hp"], boss["hp"]
    session.boss_base_def, session.boss_attacks = boss.get("defense", 0.0), boss.get("attacks", [])
    session.boss_ultimate = boss.get("ultimate")
    session.boss_reward = boss.get("reward", 0) 
    
    await ctx.send(f"🚨 **Появился босс: {session.boss_name} [❤️ {session.boss_hp} HP]!**\nНаграда за убийство: **{session.boss_reward} золота** 💰\nПишите: `!присоединиться [класс]`")
    await asyncio.sleep(60)

    if len(session.players) == 0:
        session.state = "IDLE"
        return await ctx.send("😔 Никто не пришел.")

    for i in range(1, 8 - len(session.players)):
        bot_id = f"npc_bot{i}"
        npc_stats = database.get_total_stats(bot_id)
        max_hp = npc_stats["VIT"] * 10
        session.players[bot_id] = {"id": bot_id, "name": bot_id, "class": random.choice(config.AVAILABLE_CLASSES), "hp": max_hp, "max_hp": max_hp, "is_alive": True, "is_npc": True, "strafe_turns": 0, "debuffs": []}

    session.state = "BATTLING"
    session.turn_order = list(session.players.keys())
    random.shuffle(session.turn_order)
    
    battle_msg = await ctx.send(content="⚔️ **Битва начинается!**", file=generate_battle_image())
    status_msg = await ctx.send(content=generate_status_text())
    await asyncio.sleep(2)

    while session.boss_hp > 0:
        if not [p for p in session.players.values() if p["is_alive"]]: break
        clean_dead_casters()
        
        if not session.turn_order: break
            
        p_id = session.turn_order[0]
        player = session.players[p_id]
        
        if not player["is_alive"]:
            popped = session.turn_order.pop(0)
            if player.get("is_skeleton"):
                session.turn_order.append(popped)
            continue

        action_text, tick_text, dmg = "", "", 0
        is_ode = False
        boss_trigger = False

        if player.get("is_npc"):
            skill = random.choice(config.CLASS_SKILLS[player["class"]])
            await battle_msg.edit(content=f"🤖 **Ходит {player['name']} ({player['class']}).**", attachments=[generate_battle_image(p_id)], view=None)
            await asyncio.sleep(1.5)
        else:
            view = TurnButtons(player)
            await battle_msg.edit(content=f"🛑 **Ход <@{player['id']}> ({player['class']}).** Выберите навык:", attachments=[generate_battle_image(p_id)], view=view)
            await view.wait()
            skill = view.chosen_skill
            
        target_id = None
        if skill and skill.get("target") == "ally":
            allies = [p for p in session.players.values() if p["is_alive"] and p["id"] != p_id and not (skill["id"] == "bard_ode" and p["class"] == "бард")]
            if player.get("is_npc"):
                target_id = str(random.choice(allies)["id"]) if allies else None
            else:
                if allies:
                    t_view = TargetView(player, skill, allies)
                    await battle_msg.edit(content=f"🎯 Выберите цель для **{skill['name']}**:", view=t_view)
                    await t_view.wait()
                    target_id = str(t_view.chosen_target) if t_view.chosen_target else None

        if skill is None:
            action_text += f"\n💤 Пропустил свой ход!"
        else:
            action_text, dmg, is_ode = execute_skill(p_id, player, skill, target_id)

        if not is_ode and session.boss_hp > 0:
            tick_text, boss_trigger = process_global_tick(p_id)

        if session.turn_order and session.turn_order[0] == p_id:
            popped = session.turn_order.pop(0)
            if player["is_alive"] or player.get("is_skeleton"): 
                session.turn_order.append(popped)
        
        status_content = generate_status_text()
        await battle_msg.edit(content=f"⚔️ <@{p_id}> {action_text}{tick_text} (У босса: {session.boss_hp} HP)", attachments=[generate_battle_image(None, boss_trigger)], view=None)
        await status_msg.edit(content=status_content)
        
        lines_count = status_content.count('\n') + action_text.count('\n') + tick_text.count('\n')
        delay = max(5.0, min(14.0, 4.0 + (lines_count * 0.4)))
        await asyncio.sleep(delay)

        if session.boss_hp <= 0: break

        if boss_trigger:
            alive_players = [p for p in session.players.values() if p["is_alive"]]
            if not alive_players: break
                
            boss_atk_text, death_reports = execute_boss_attack(alive_players)

            status_content = generate_status_text()
            await battle_msg.edit(content=f"{boss_atk_text}{death_reports}", attachments=[generate_battle_image()], view=None)
            await status_msg.edit(content=status_content)
            
            lines_count = status_content.count('\n') + boss_atk_text.count('\n') + death_reports.count('\n')
            delay = max(5.0, min(14.0, 4.0 + (lines_count * 0.4)))
            await asyncio.sleep(delay)

    if session.boss_hp <= 0: 
        reward_text = ""
        for p in session.players.values():
            if not p.get("is_npc"):
                database.add_gold(p["id"], session.boss_reward)
                reward_text += f"<@{p['id']}> "
                
        victory_msg = f"🎉 **ПОБЕДА!** **{session.boss_name}** повержен! 🏆\n"
        if reward_text:
            victory_msg += f"💰 Отряд получает награду по **{session.boss_reward} золота**: {reward_text}"
            
        await battle_msg.edit(content=victory_msg, attachments=[generate_endgame_image(is_victory=True)], view=None)
    else: 
        await battle_msg.edit(content=f"💀 **ПОРАЖЕНИЕ...** Отряд уничтожен.", attachments=[generate_endgame_image(is_victory=False)], view=None)
        
    session.state = "IDLE"

@bot.command(name="присоединиться", aliases=["join"])
async def join_game(ctx, role: str = None):
    if session.state != "RECRUITING": return
    if not role or role.lower() not in config.AVAILABLE_CLASSES: return await ctx.send(f"❌ Классы: {', '.join(config.AVAILABLE_CLASSES)}")
    if str(ctx.author.id) in session.players: return
    
    database.get_player(ctx.author.id, ctx.author.display_name) 
    stats = database.get_total_stats(ctx.author.id)
    max_hp = stats["VIT"] * 10
    
    session.players[str(ctx.author.id)] = {"id": ctx.author.id, "name": ctx.author.display_name, "class": role.lower(), "hp": max_hp, "max_hp": max_hp, "is_alive": True, "is_npc": False, "strafe_turns": 0, "debuffs": []}
    await ctx.send(f"✅ {ctx.author.mention} готов как **{role}** (❤️ {max_hp} HP)!")

bot.run(os.getenv('DISCORD_TOKEN'))