import discord
import config
import database
from collections import Counter

# === МЕНЮ ВЫБОРА ЦЕЛИ ===
class TargetSelect(discord.ui.Select):
    def __init__(self, player, skill, allies):
        opts = [discord.SelectOption(label=a["name"], description=f"Класс: {a['class']} | HP: {a['hp']}/{a['max_hp']}", value=str(a["id"])) for a in allies]
        super().__init__(placeholder="Выберите союзника...", options=opts)
        self.player, self.skill = player, skill

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.player["id"]):
            await interaction.response.send_message("❌ Не ваш ход!", ephemeral=True)
            return
        self.view.chosen_target = self.values[0]
        self.view.stop()
        await interaction.response.defer()

class TargetView(discord.ui.View):
    def __init__(self, player, skill, allies, timeout=30):
        super().__init__(timeout=timeout)
        self.chosen_target = None
        self.add_item(TargetSelect(player, skill, allies))

# === КНОПКИ ДЕЙСТВИЙ ИГРОКА ===
class TurnButtons(discord.ui.View):
    def __init__(self, player, timeout=30):
        super().__init__(timeout=timeout)
        self.player = player
        self.chosen_skill = None
        for skill in config.CLASS_SKILLS.get(player["class"], []):
            btn = discord.ui.Button(label=skill["name"], custom_id=skill["id"], style=discord.ButtonStyle.primary)
            btn.callback = self.make_callback(skill)
            self.add_item(btn)
        info_btn = discord.ui.Button(label="ℹ️ Описание", custom_id=f"info_{player['id']}", style=discord.ButtonStyle.secondary)
        info_btn.callback = self.show_skills_info
        self.add_item(info_btn)

    def make_callback(self, skill):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != str(self.player["id"]): return await interaction.response.send_message("❌ Не ваш ход!", ephemeral=True)
            self.chosen_skill = skill
            for item in self.children: item.disabled = True
            await interaction.response.defer()
            self.stop()
        return callback

    async def show_skills_info(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.player["id"]): return
        text = f"📖 **Шпаргалка [{self.player['class'].upper()}]:**\n\n"
        for s in config.CLASS_SKILLS.get(self.player["class"], []): text += f"• **{s['name']}**\n  └ *{s.get('desc', '')}*\n\n"
        await interaction.response.send_message(text, ephemeral=True)

# === ИНТЕРФЕЙС ПРОФИЛЯ И ЭКИПИРОВКИ ===
class EquipItemView(discord.ui.View):
    def __init__(self, user_id, slot):
        super().__init__(timeout=60)
        self.user_id = str(user_id)
        self.slot = slot
        
        player = database.get_player(user_id)
        inv = player.get("inventory", [])
        
        valid_items = {}
        if slot == "weapon": valid_items = config.ITEMS_DB.get("weapons", {})
        elif slot == "armor": valid_items = config.ITEMS_DB.get("armor", {})
        elif slot.startswith("acc"): valid_items = config.ITEMS_DB.get("accessories", {})
        
        options = [discord.SelectOption(label="Снять снаряжение", value="none", emoji="❌")]
        
        added_items = set()
        for item_id in inv:
            if item_id in valid_items and item_id not in added_items:
                item = valid_items[item_id]
                options.append(discord.SelectOption(label=item["name"], value=item_id))
                added_items.add(item_id)
                if len(options) >= 25: break
                
        self.select = discord.ui.Select(placeholder="Выберите предмет...", options=options)
        self.select.callback = self.item_callback
        self.add_item(self.select)
        
    async def item_callback(self, interaction: discord.Interaction):
        item_id = self.select.values[0]
        if item_id == "none":
            database.unequip_item(self.user_id, self.slot)
            await interaction.response.edit_message(content="✅ Снаряжение снято! Пропишите `!профиль` для обновления.", view=None)
        else:
            database.equip_item(self.user_id, self.slot, item_id)
            await interaction.response.edit_message(content="✅ Снаряжение надето! Пропишите `!профиль` для обновления.", view=None)

class EquipSlotView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = str(user_id)
        options = [
            discord.SelectOption(label="Оружие", value="weapon", emoji="⚔️"),
            discord.SelectOption(label="Броня", value="armor", emoji="🛡️"),
            discord.SelectOption(label="Аксессуар 1", value="acc1", emoji="💍"),
            discord.SelectOption(label="Аксессуар 2", value="acc2", emoji="💍")
        ]
        self.select = discord.ui.Select(placeholder="Какой слот изменить?", options=options)
        self.select.callback = self.slot_callback
        self.add_item(self.select)
        
    async def slot_callback(self, interaction: discord.Interaction):
        slot = self.select.values[0]
        await interaction.response.edit_message(content=f"Слот **{slot}**. Теперь выберите предмет из инвентаря:", view=EquipItemView(self.user_id, slot))

class ProfileView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = str(user_id)

    @discord.ui.button(label="🎒 Инвентарь", style=discord.ButtonStyle.secondary)
    async def btn_inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Это не ваш профиль!", ephemeral=True)
        
        player = database.get_player(self.user_id)
        inv = player.get("inventory", [])
        
        if not inv: return await interaction.response.send_message("🕸️ Ваш инвентарь абсолютно пуст.", ephemeral=True)
        
        all_items = {**config.ITEMS_DB.get("weapons", {}), **config.ITEMS_DB.get("armor", {}), **config.ITEMS_DB.get("accessories", {})}
        text = "🎒 **Ваш инвентарь:**\n"
        counts = Counter(inv)
        for item_id, count in counts.items():
            item = all_items.get(item_id)
            if item: text += f"• {item['name']} (x{count})\n"
                
        await interaction.response.send_message(text, ephemeral=True)

    @discord.ui.button(label="👕 Снаряжение", style=discord.ButtonStyle.primary)
    async def btn_equip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Это не ваш профиль!", ephemeral=True)
        await interaction.response.send_message("⚙️ Управление экипировкой:", view=EquipSlotView(self.user_id), ephemeral=True)

# === ИНТЕРФЕЙС МАГАЗИНА ===
class ShopSelect(discord.ui.Select):
    def __init__(self, user_id):
        self.user_id = str(user_id)
        options = []
        self.all_items = {**config.ITEMS_DB.get("weapons", {}), **config.ITEMS_DB.get("armor", {}), **config.ITEMS_DB.get("accessories", {})}
        
        for i_id, item in self.all_items.items():
            price = item.get("price", 99999)
            stats_str = ", ".join([f"{k}+{v}" for k,v in item.get("stats", {}).items()])
            desc = f"💰 {price} | {stats_str}"
            options.append(discord.SelectOption(label=item["name"], description=desc, value=i_id))
            if len(options) >= 25: break 
            
        super().__init__(placeholder="Выберите предмет для покупки...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Вы не можете использовать это меню!", ephemeral=True)
        
        item_id = self.values[0]
        item = self.all_items[item_id]
        price = item.get("price", 99999)
        
        if database.spend_gold(self.user_id, price):
            database.add_item(self.user_id, item_id)
            await interaction.response.send_message(f"🎉 Вы успешно купили **{item['name']}**! Предмет добавлен в инвентарь.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Недостаточно золота. Нужно: {price} 💰", ephemeral=True)

class ShopView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.add_item(ShopSelect(user_id))