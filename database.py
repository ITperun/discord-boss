import json
import os
import config

DB_FILE = "players.json"

BASE_STATS = {"STR": 10, "AGI": 10, "INT": 10, "VIT": 10, "CHA": 10, "DEX": 0, "LUK": 0}

def load_db():
    if not os.path.exists(DB_FILE): return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except json.JSONDecodeError: return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_player(user_id, display_name="Unknown"):
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = {
            "name": display_name,
            "gold": 0,
            "inventory": [], 
            "equipment": {"weapon": None, "armor": None, "acc1": None, "acc2": None}
        }
        save_db(db)
    else:
        # Патч для старых профилей
        updated = False
        if "inventory" not in db[uid]:
            db[uid]["inventory"] = []
            updated = True
        if "equipment" not in db[uid]:
            db[uid]["equipment"] = {"weapon": None, "armor": None, "acc1": None, "acc2": None}
            updated = True
        if updated: save_db(db)
            
    return db[uid]

def add_gold(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid in db:
        db[uid]["gold"] += amount
        save_db(db)

def spend_gold(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid in db and db[uid]["gold"] >= amount:
        db[uid]["gold"] -= amount
        save_db(db)
        return True
    return False

def add_item(user_id, item_id):
    db = load_db()
    uid = str(user_id)
    if uid in db:
        db[uid]["inventory"].append(item_id)
        save_db(db)

# 🔥 НОВАЯ ФУНКЦИЯ ДЛЯ ПРОДАЖИ (Удаление предмета)
def remove_item(user_id, item_id):
    db = load_db()
    uid = str(user_id)
    if uid in db and item_id in db[uid]["inventory"]:
        # Удаляем только одну копию предмета
        db[uid]["inventory"].remove(item_id)
        
        # Если такого предмета больше не осталось в инвентаре, снимаем его с экипировки
        if item_id not in db[uid]["inventory"]:
            for slot, eq_id in db[uid]["equipment"].items():
                if eq_id == item_id:
                    db[uid]["equipment"][slot] = None
                    
        save_db(db)
        return True
    return False

def equip_item(user_id, slot, item_id):
    db = load_db()
    uid = str(user_id)
    if uid in db and item_id in db[uid]["inventory"]:
        db[uid]["equipment"][slot] = item_id
        save_db(db)
        return True
    return False

def unequip_item(user_id, slot):
    db = load_db()
    uid = str(user_id)
    if uid in db:
        db[uid]["equipment"][slot] = None
        save_db(db)

def get_total_stats(user_id):
    uid = str(user_id)
    if uid.startswith("npc_"): return BASE_STATS.copy()
    
    db = load_db()
    if uid not in db: return BASE_STATS.copy()
    
    player = db[uid]
    total_stats = BASE_STATS.copy()
    
    all_items = {**config.ITEMS_DB.get("weapons", {}), 
                 **config.ITEMS_DB.get("armor", {}), 
                 **config.ITEMS_DB.get("accessories", {})}
    
    for slot, item_id in player["equipment"].items():
        if item_id and item_id in all_items:
            item_stats = all_items[item_id].get("stats", {})
            for stat_name, val in item_stats.items():
                if stat_name in total_stats:
                    total_stats[stat_name] += val
                    
    return total_stats