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

# === ОБНОВЛЕННЫЙ МАГАЗИН (Сортировка, Страницы, Модальное окно) ===
class PageModal(discord.ui.Modal, title="Переход на страницу"):
    page_num = discord.ui.TextInput(
        label="Введите номер страницы",
        style=discord.TextStyle.short,
        placeholder="Например: 2",
        required=True,
        max_length=3
    )

    def __init__(self, shop_view):
        super().__init__()
        self.shop_view = shop_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_num.value)
            items_list = self.shop_view.get_sorted_items()
            total_pages = max(1, (len(items_list) + 9) // 10)
            
            if page < 1 or page > total_pages:
                return await interaction.response.send_message(f"❌ Страница должна быть от 1 до {total_pages}.", ephemeral=True)
                
            self.shop_view.current_page = page
            self.shop_view.update_components()
            await interaction.response.edit_message(embed=self.shop_view.generate_embed(), view=self.shop_view)
        except ValueError:
            await interaction.response.send_message("❌ Введите корректное число.", ephemeral=True)

class ShopSelect(discord.ui.Select):
    def __init__(self, user_id, page_items):
        self.user_id = str(user_id)
        self.page_items = page_items
        options = []
        
        for i_id, item in self.page_items:
            price = item.get("price", 99999)
            stats_str = ", ".join([f"{k} {v if v<0 else '+'+str(v)}" for k,v in item.get("stats", {}).items()])
            desc = f"💰 {price} | {stats_str}"[:100]
            options.append(discord.SelectOption(label=item["name"][:25], description=desc, value=i_id))
            
        if not options:
            options.append(discord.SelectOption(label="Пусто", value="none"))
            
        super().__init__(placeholder="Выберите предмет для покупки...", options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Вы не можете использовать это меню!", ephemeral=True)
        
        item_id = self.values[0]
        if item_id == "none":
            return await interaction.response.send_message("Здесь пока нет товаров.", ephemeral=True)
            
        item_dict = dict(self.page_items)
        item = item_dict[item_id]
        price = item.get("price", 99999)
        
        if database.spend_gold(self.user_id, price):
            database.add_item(self.user_id, item_id)
            await interaction.response.send_message(f"🎉 Вы успешно купили **{item['name']}**! Предмет добавлен в инвентарь.", ephemeral=True)
            
            if hasattr(self.view, "generate_embed"):
                await interaction.message.edit(embed=self.view.generate_embed(), view=self.view)
        else:
            await interaction.response.send_message(f"❌ Недостаточно золота. Нужно: {price} 💰", ephemeral=True)

class ShopView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = str(user_id)
        self.current_category = "weapons"
        self.current_page = 1
        self.update_components()

    def get_sorted_items(self):
        items_dict = config.ITEMS_DB.get(self.current_category, {})
        items_list = list(items_dict.items())
        items_list.sort(key=lambda x: x[1].get("price", 999999))
        return items_list

    def get_page_items(self):
        items_list = self.get_sorted_items()
        start = (self.current_page - 1) * 10
        return items_list[start:start+10]

    def update_components(self):
        self.clear_items()
        
        btn_weap = discord.ui.Button(label="⚔️ Оружие", style=discord.ButtonStyle.primary if self.current_category == "weapons" else discord.ButtonStyle.secondary, row=0)
        btn_weap.callback = self.make_cat_callback("weapons")
        
        btn_arm = discord.ui.Button(label="🛡️ Броня", style=discord.ButtonStyle.primary if self.current_category == "armor" else discord.ButtonStyle.secondary, row=0)
        btn_arm.callback = self.make_cat_callback("armor")
        
        btn_acc = discord.ui.Button(label="💍 Аксессуары", style=discord.ButtonStyle.primary if self.current_category == "accessories" else discord.ButtonStyle.secondary, row=0)
        btn_acc.callback = self.make_cat_callback("accessories")
        
        self.add_item(btn_weap)
        self.add_item(btn_arm)
        self.add_item(btn_acc)
        
        items_list = self.get_sorted_items()
        total_pages = max(1, (len(items_list) + 9) // 10)
        if self.current_page > total_pages: 
            self.current_page = total_pages
        
        btn_prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, disabled=(self.current_page == 1), row=1)
        btn_prev.callback = self.page_prev
        
        btn_page = discord.ui.Button(label=f"Стр. {self.current_page}/{total_pages} (Ввод)", style=discord.ButtonStyle.secondary, row=1)
        btn_page.callback = self.page_input
        
        btn_next = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, disabled=(self.current_page == total_pages), row=1)
        btn_next.callback = self.page_next
        
        self.add_item(btn_prev)
        self.add_item(btn_page)
        self.add_item(btn_next)
        
        page_items = self.get_page_items()
        self.add_item(ShopSelect(self.user_id, page_items))

    def make_cat_callback(self, category):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.user_id:
                return await interaction.response.send_message("❌ Не ваше меню!", ephemeral=True)
            self.current_category = category
            self.current_page = 1 
            self.update_components()
            embed = self.generate_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        return callback

    async def page_prev(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id: return
        self.current_page -= 1
        self.update_components()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def page_next(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id: return
        self.current_page += 1
        self.update_components()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def page_input(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Не ваше меню!", ephemeral=True)
        await interaction.response.send_modal(PageModal(self))

    def generate_embed(self):
        cat_name = {"weapons": "⚔️ Оружие", "armor": "🛡️ Броня", "accessories": "💍 Аксессуары"}.get(self.current_category, "Предметы")
        
        items_list = self.get_sorted_items()
        total_pages = max(1, (len(items_list) + 9) // 10)
        page_items = self.get_page_items()
        
        embed = discord.Embed(title="🛒 Магазин Снаряжения", color=discord.Color.gold())
        embed.description = f"**Категория:** {cat_name}\n**Страница {self.current_page} из {total_pages}**\n\n"
        
        if not page_items:
            embed.description += "*Здесь пока нет товаров.*"
        else:
            for i_id, item in page_items:
                stats = ", ".join([f"**{k}**: {v if v<0 else '+'+str(v)}" for k, v in item.get("stats", {}).items()])
                embed.description += f"**{item['name']}** — 💰 {item.get('price', 9999)}\n└ Статы: {stats}\n\n"
                
        player = database.get_player(self.user_id)
        embed.set_footer(text=f"Твой кошелек: {player.get('gold', 0)} золота")
        
        return embed

# === ИНТЕРФЕЙС РЕЙТИНГА ИГРОКОВ ===
class LeaderboardView(discord.ui.View):
    def __init__(self, top_players):
        super().__init__(timeout=120)
        self.top_players = top_players
        self.current_page = 1
        # Рассчитываем точное количество страниц (каждая вмещает до 10 игроков)
        self.max_pages = max(1, (len(top_players) + 9) // 10)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.max_pages > 1:
            btn_prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, disabled=(self.current_page == 1))
            btn_prev.callback = self.prev_page
            
            btn_next = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, disabled=(self.current_page == self.max_pages))
            btn_next.callback = self.next_page
            
            self.add_item(btn_prev)
            self.add_item(btn_next)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    def generate_embed(self):
        embed = discord.Embed(title="🏆 Топ богатейших авантюристов", color=discord.Color.gold())
        
        start_idx = (self.current_page - 1) * 10
        end_idx = start_idx + 10
        page_players = self.top_players[start_idx:end_idx]

        desc = ""
        for i, p in enumerate(page_players):
            rank = start_idx + i + 1
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "🏅"
            desc += f"**{rank}.** {medal} **{p.get('name', 'Неизвестный')}** — 💰 {p.get('gold', 0)}\n"

        if not desc:
            desc = "Пока ни один авантюрист не накопил богатств."

        embed.description = desc
        embed.set_footer(text=f"Страница {self.current_page} из {self.max_pages}")
        
        return embed