import discord
import config

class TargetSelect(discord.ui.Select):
    def __init__(self, player, skill, allies):
        opts = [discord.SelectOption(label=a["name"], description=f"Класс: {a['class']} | HP: {a['hp']}", value=str(a["id"])) for a in allies]
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