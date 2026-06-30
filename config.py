import json

CLASS_SKILLS = {}
BOSSES_LIST = []
VIEW_CONFIG = {}
AVAILABLE_CLASSES = []

def reload_data():
    global CLASS_SKILLS, BOSSES_LIST, VIEW_CONFIG, AVAILABLE_CLASSES
    
    with open("skills.json", "r", encoding="utf-8") as f:
        CLASS_SKILLS = json.load(f)
        
    with open("bosses.json", "r", encoding="utf-8") as f:
        BOSSES_LIST = json.load(f)
        
    with open("view_config.json", "r", encoding="utf-8") as f:
        VIEW_CONFIG = json.load(f)
        
    AVAILABLE_CLASSES = list(CLASS_SKILLS.keys())

# Подгружаем данные при первом запуске
reload_data()