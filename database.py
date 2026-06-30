import json
import os

DB_FILE = "wallets.json"

def load_wallets():
    """Загружает базу данных кошельков. Если файла нет, возвращает пустой словарь."""
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_wallets(wallets):
    """Сохраняет данные кошельков в файл."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(wallets, f, indent=4, ensure_ascii=False)

def add_gold(user_id, amount):
    """Добавляет золото указанному пользователю. Создает кошелек, если его не было."""
    wallets = load_wallets()
    user_id_str = str(user_id)
    
    if user_id_str not in wallets:
        wallets[user_id_str] = {"gold": 0}
        
    wallets[user_id_str]["gold"] += amount
    save_wallets(wallets)