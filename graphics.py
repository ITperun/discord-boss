import os
import io
import discord
from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji  # <--- Новый импорт для эмодзи
import config
from game_state import session

def get_player_sprite(class_name):
    cfg = config.VIEW_CONFIG["spritesheet"]
    if not os.path.exists(cfg["path"]): return None
    try:
        sheet = Image.open(cfg["path"]).convert("RGBA")
        frame_w = sheet.width // cfg["columns"]
        frame_h = sheet.height // cfg["rows"]
        col, row = cfg["mapping"].get(class_name, (0,0))
        return sheet.crop((col * frame_w, row * frame_h, col * frame_w + frame_w, row * frame_h + frame_h))
    except Exception: return None

def generate_battle_image(current_player_id=None, boss_action_ready=False):
    boss_cfg = config.VIEW_CONFIG["boss_display"]
    party_cfg = config.VIEW_CONFIG["party_display"]

    bg_map = {
        "Орк-Разрушитель": "assets/background-orc.png",
        "Древний Дракон": "assets/background-dragon.png",
        "Проклятый Некромант": "assets/background-necro.png"
    }
    bg_path = bg_map.get(session.boss_name, "assets/background.png")

    try:
        bg = Image.open(bg_path).convert("RGBA")
    except FileNotFoundError:
        try:
            bg = Image.open("assets/background.png").convert("RGBA")
        except FileNotFoundError:
            bg = Image.new("RGBA", (1200, 400), (40, 40, 40, 255))
        
    draw = ImageDraw.Draw(bg)
    
    try:
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        font_hp = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
    except IOError:
        font_name = ImageFont.load_default()
        font_hp = ImageFont.load_default()

    boss_filename = f"assets/{session.boss_name.lower().replace(' ', '-')}.png"
    if not os.path.exists(boss_filename): boss_filename = "assets/boss.png"

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
    
    total_def = session.boss_base_def - sum(b["value"] for b in session.boss_debuffs["def_down"].values())
    alive_count = len([p for p in session.players.values() if p["is_alive"]])
    max_cd = 3 if alive_count >= 5 else 2 if alive_count >= 3 else 1
    
    # Полоска ХП босса
    draw.rectangle([boss_x, boss_y - 20, boss_x + boss_w, boss_y - 10], fill=(60, 20, 20))
    hp_percent = session.boss_hp / session.boss_max_hp
    draw.rectangle([boss_x, boss_y - 20, boss_x + int(boss_w * hp_percent), boss_y - 10], fill=(220, 40, 40))
    
    # 🔥 ИСПОЛЬЗУЕМ PILMOJI ДЛЯ ОТРИСОВКИ ТЕКСТА С ЭМОДЗИ НА ПОЛЕ БОЯ
    with Pilmoji(bg) as pilmoji:
        pilmoji.text((boss_x, boss_y - 60), f"👹 {session.boss_name} (🛡️ Защита: {int(total_def*100)}%)", fill="white", font=font_name)
        cd_text = "⚠️ ПОДГОТОВКА УДАРА!" if boss_action_ready else f"⏳ Очередь атаки: {session.boss_cooldown_counter}/{max_cd}"
        pilmoji.text((boss_x, boss_y - 45), cd_text, fill="orange" if boss_action_ready else "#87CEEB", font=font_name)
        pilmoji.text((boss_x + 5, boss_y - 21), f"{session.boss_hp} / {session.boss_max_hp} HP", fill="white", font=font_hp)

    p_w, p_h = party_cfg["sprite_width"], party_cfg["sprite_height"]
    start_x, spacing_x, base_y = party_cfg["start_x"], party_cfg["spacing_x"], party_cfg["base_y"]

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
        
        # Полоска ХП игроков
        draw.rectangle([x, y - 15, x + p_w, y - 8], fill=(60, 20, 20))
        p_hp_percent = player["hp"] / player["max_hp"]
        draw.rectangle([x, y - 15, x + int(p_w * p_hp_percent), y - 8], fill=(40, 220, 40))
        
        # Текст имени игрока с эмодзи
        with Pilmoji(bg) as pilmoji:
            pilmoji.text((x, y - 35), p_name, fill=name_color, font=font_name)

    img_byte_arr = io.BytesIO()
    bg.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return discord.File(fp=img_byte_arr, filename="battle.png")

def generate_profile_image(player_data, total_stats, avatar_bytes=None):
    bg = Image.new("RGBA", (600, 300), (30, 30, 35, 255))
    draw = ImageDraw.Draw(bg)
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
    except:
        font_title = font_text = ImageFont.load_default()

    # Отрисовка аватара
    if avatar_bytes:
        try:
            avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar_img = avatar_img.resize((150, 150), Image.Resampling.LANCZOS)
            bg.paste(avatar_img, (20, 20), avatar_img)
        except Exception:
            draw.rectangle([20, 20, 170, 170], fill=(60, 60, 70))
            draw.text((45, 80), "АВАТАР", fill="white", font=font_text)
    else:
        draw.rectangle([20, 20, 170, 170], fill=(60, 60, 70))
        draw.text((45, 80), "АВАТАР", fill="white", font=font_text)
    
    all_items = {**config.ITEMS_DB.get("weapons", {}), **config.ITEMS_DB.get("armor", {}), **config.ITEMS_DB.get("accessories", {})}

    eq = player_data["equipment"]
    wep_name = all_items[eq["weapon"]]["name"] if eq["weapon"] in all_items else "Пусто"
    arm_name = all_items[eq["armor"]]["name"] if eq["armor"] in all_items else "Пусто"
    ac1_name = all_items[eq["acc1"]]["name"] if eq["acc1"] in all_items else "Пусто"
    ac2_name = all_items[eq["acc2"]]["name"] if eq["acc2"] in all_items else "Пусто"
    max_hp = total_stats["VIT"] * 10

    # 🔥 ИСПОЛЬЗУЕМ PILMOJI ДЛЯ ТЕКСТА ПРОФИЛЯ
    with Pilmoji(bg) as pilmoji:
        pilmoji.text((20, 185), f"👤 {player_data['name']}", fill="#FFD700", font=font_title)
        pilmoji.text((20, 225), f"💰 Золото: {player_data['gold']}", fill="yellow", font=font_text)

        pilmoji.text((210, 20), "ЭКИПИРОВКА", fill="#87CEEB", font=font_title)
        y_eq = 60
        pilmoji.text((210, y_eq), f"⚔️ Оружие: {wep_name}", fill="white", font=font_text); y_eq+=35
        pilmoji.text((210, y_eq), f"🛡️ Броня: {arm_name}", fill="white", font=font_text); y_eq+=35
        pilmoji.text((210, y_eq), f"💍 Аксесс 1: {ac1_name}", fill="white", font=font_text); y_eq+=35
        pilmoji.text((210, y_eq), f"💍 Аксесс 2: {ac2_name}", fill="white", font=font_text)

        pilmoji.text((450, 20), "АТРИБУТЫ", fill="#FF6347", font=font_title)
        y = 60
        pilmoji.text((450, y), f"❤️ HP: {max_hp}", fill="#32CD32", font=font_text); y+=30
        pilmoji.text((450, y), f"💪 STR: {total_stats['STR']}", fill="white", font=font_text); y+=30
        pilmoji.text((450, y), f"🏹 AGI: {total_stats['AGI']}", fill="white", font=font_text); y+=30
        pilmoji.text((450, y), f"🔮 INT: {total_stats['INT']}", fill="white", font=font_text); y+=30
        pilmoji.text((450, y), f"🎵 CHA: {total_stats['CHA']}", fill="white", font=font_text); y+=30
        pilmoji.text((450, y), f"💨 DEX: {total_stats['DEX']}%", fill="white", font=font_text); y+=30
        pilmoji.text((450, y), f"🍀 LUK: {total_stats['LUK']}%", fill="white", font=font_text)

    img_byte_arr = io.BytesIO()
    bg.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return discord.File(fp=img_byte_arr, filename="profile.png")