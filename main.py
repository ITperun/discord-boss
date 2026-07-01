import discord
from discord.ext import commands
import asyncio
import random
import os
from dotenv import load_dotenv

import config
from game_state import session
import database
# 🔥 Импортируем новую функцию экрана конца игры
from graphics import generate_battle_image, generate_profile_image, generate_endgame_image
from effects import generate_status_text
from combat import clean_dead_casters, execute_skill, process_global_tick, execute_boss_attack
from ui import TurnButtons, TargetView, ProfileView, ShopView

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready(): 
    print(f'✅ Бот {bot.user} запущен и модули загружены!')

@bot.command(name="кошелек")
async def check_wallet(ctx):
    player = database.get_player(ctx.author.id, ctx.author.display_name)
    await ctx.send(f"💰 {ctx.author.mention}, в твоем кошельке **{player['gold']} золота**.")

@bot.command(name="профиль")
async def show_profile(ctx):
    player_data = database.get_player(ctx.author.id, ctx.author.display_name)
    stats = database.get_total_stats(ctx.author.id)
    
    avatar_bytes = None
    try:
        avatar_bytes = await ctx.author.display_avatar.replace(size=256, format="png").read()
    except Exception as e:
        print(f"Не удалось загрузить аватар: {e}")
        
    file = generate_profile_image(player_data, stats, avatar_bytes)
    view = ProfileView(ctx.author.id)
    await ctx.send(file=file, view=view)

@bot.command(name="магазин", aliases=["shop"])
async def show_shop(ctx):
    config.reload_data()
    view = ShopView(ctx.author.id)
    await ctx.send("🛒 **Добро пожаловать в Магазин!**\nПотратьте заработанное с боссов золото с умом:", view=view)

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
            session.turn_order.pop(0)
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
            if player["is_alive"]: session.turn_order.append(popped)
        
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

    # 🔥 ЗАМЕНЯЕМ КАРТИНКУ НА ЭКРАН ПОБЕДЫ ИЛИ ПОРАЖЕНИЯ
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