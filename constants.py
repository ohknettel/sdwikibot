wiki_colour = 0x061442
archives_colour = 0x6e4e36
neutral_colour = 0x0B1215

import discord, typing

class EmbedPaginatorView(discord.ui.View):
    curitem: discord.Embed
    message: typing.Optional[discord.InteractionMessage]

    def __init__(self, user: typing.Union[discord.User, discord.Member]):
        super().__init__(timeout=180)
        self.user = user
        self.curindex = 0
        self.items = []
        self.message = None

    def add_embed(self, embed: discord.Embed):
        self.items.append(embed)
        return self

    @discord.ui.button(label="Next Page", custom_id="next", style=discord.ButtonStyle.green)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user == self.user:
            await interaction.response.send_message("You are not the executor of this command!", ephemeral=True)
            return;

        await interaction.response.defer()

        if 0 <= (newindex := self.curindex + 1) < len(self.items):
            self.curindex = newindex
            self.curitem = self.items[newindex]

        if self.curindex == len(self.items) - 1:
            button.disabled = True

        prev_btn = next((c for c in self.children if isinstance(c, discord.ui.Button) and c.custom_id == "previous"), None)
        if prev_btn and self.curindex > 0:
            prev_btn.disabled = False

        self.message = await interaction.edit_original_response(embed=self.curitem, view=self)

    @discord.ui.button(label="Previous Page", custom_id="previous", style=discord.ButtonStyle.gray, disabled=True)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user == self.user:
            await interaction.response.send_message("You are not the executor of this command!", ephemeral=True)
            return;

        await interaction.response.defer()

        if 0 <= (newindex := self.curindex - 1) < len(self.items):
            self.curindex = newindex
            self.curitem = self.items[newindex]

        if self.curindex == 0:
            button.disabled = True

        next_btn = next((c for c in self.children if isinstance(c, discord.ui.Button) and c.custom_id == "next"), None)
        if next_btn and self.curindex < len(self.items) - 1:
            next_btn.disabled = False

        self.message = await interaction.edit_original_response(embed=self.curitem, view=self)

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            self.curitem.set_footer(text=(self.curitem.footer.text or "") + " | Embed timed out")
            await self.message.edit(embed=self.curitem, view=self)
