class GameSession:
    def __init__(self):
        self.state = "IDLE"
        self.players = {}
        self.boss_name = ""
        self.boss_hp = 0
        self.boss_max_hp = 0
        self.boss_base_def = 0.0
        self.boss_reward = 0    
        self.boss_attacks = []
        self.boss_ultimate = None 
        self.turn_order = []
        
        self.party_buffs = {"atk": {}, "def": {}, "regen": [], "vamp": {}}
        self.boss_debuffs = {"def_down": {}, "atk_down": {}, "dots": []}
        
        self.boss_cooldown_counter = 0 
        self.boss_turns_taken = 0      
        self.boss_slow_stacks = 0

        # Новые переменные для механики Дракона
        self.dragon_in_flight = False
        self.dragon_flight_timer = 0
        self.dragon_flight_damage = 0
        self.dragon_flight_threshold = 0

    def reset(self):
        self.__init__()

session = GameSession()