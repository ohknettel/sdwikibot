from tinydb import Query
from tinydb.operations import set as tset
from bot import SDWB2
from discord.ext.commands import Cog
from discord import app_commands
import discord

class PrefCog(Cog):
	def __init__(self, bot: SDWB2):
		self.bot = bot

	group = app_commands.Group(name="preferences", description="Configure SD Wikibot.")

	@group.command(name="list", description="Lists the current configuration of SD Wikibot in this guild.")
	async def _list(self, interaction: discord.Interaction):
		assert(interaction.guild)

		preferences = await self.bot.get_guild_preferences(interaction.guild)
		emojis = self.bot.get_emojis(interaction.guild)

		message = ""

		for preference in preferences:
			key = preference["key"]
			value = preference["value"]
			description = preference.get("description")

			message += f"`{key}`"
			if isinstance(value, bool):
				message += f" {emojis.toggle_on if value else emojis.toggle_off}\n"
			elif isinstance(value, str):
				message += f" *{value}*\n"
			elif isinstance(value, int):
				message += f" ({value})\n"

			if description:
				message += f"{description}\n\n"
			else:
				message += "\n"

		await interaction.response.send_message(message)

	@app_commands.checks.has_permissions(ban_members=True)
	@group.command(description="Toggle whether smart referencing is enabled or not.")
	async def toggle_smart_referencing(self, interaction: discord.Interaction, toggle: bool | None = None):
		assert(interaction.guild)

		preferences = await self.bot.get_guild_preferences(interaction.guild)
		emojis = self.bot.get_emojis(interaction.guild)

		query = Query()
		condition = query.key == "smart_referencing"

		pref = preferences.get(condition)
		if not pref or isinstance(pref, list):
			return

		value: bool = toggle or not pref["value"]
		preferences.update(tset("value", value), condition)

		emoji = emojis.toggle_on if value else emojis.toggle_off
		wording = "on" if value else "off"

		await interaction.response.send_message(f"Toggled smart referencing {wording} {emoji}.", ephemeral=True)

	_set = app_commands.Group(name="set", description="Set SD Wikibot preferences.", parent=group)

	@app_commands.checks.has_permissions(ban_members=True)
	@app_commands.describe(silence="Whether to silence hyperlink embeds for results.")
	@_set.command(description="Set whether to show preview embeds for results returned by smart referencing.")
	async def silence_result_links(self, interaction: discord.Interaction, silence: bool):
		assert(interaction.guild)

		preferences = await self.bot.get_guild_preferences(interaction.guild)
		emojis = self.bot.get_emojis(interaction.guild)

		query = Query()
		condition = query.key == "silence_result_links"

		pref = preferences.get(condition)
		if not pref or isinstance(pref, list):
			return

		preferences.update(tset("value", silence), condition)

		if silence:
			await interaction.response.send_message(f"Silenced result links {emojis.toggle_on}.", ephemeral=True)
		else:
			await interaction.response.send_message(f"Unsilenced result links {emojis.toggle_off}.", ephemeral=True)

	@app_commands.checks.has_permissions(ban_members=True)
	@app_commands.describe(apply="Whether to apply smart referencing on message edits.")
	@_set.command(description="Set whether to apply smart referencing on message edits.")
	async def reference_on_edit(self, interaction: discord.Interaction, apply: bool):
		assert(interaction.guild)

		preferences = await self.bot.get_guild_preferences(interaction.guild)
		emojis = self.bot.get_emojis(interaction.guild)

		query = Query()
		condition = query.key == "reference_on_edit"

		pref = preferences.get(condition)
		if not pref or isinstance(pref, list):
			return

		preferences.update(tset("value", apply), condition)

		if apply:
			await interaction.response.send_message(f"Smart referencing will be applied on message edits {emojis.toggle_on}.", ephemeral=True)
		else:
			await interaction.response.send_message(f"Smart referencing will not be applied on message edits {emojis.toggle_off}.", ephemeral=True)

	@app_commands.checks.has_permissions(ban_members=True)
	@app_commands.describe(message="The message to accompany results.")
	@_set.command(description="Set the message to display when results are found.")
	async def results_message(self, interaction: discord.Interaction, message: str):
		assert(interaction.guild)

		preferences = await self.bot.get_guild_preferences(interaction.guild)

		query = Query()
		condition = query.key == "results_message"

		pref = preferences.get(condition)
		if not pref or isinstance(pref, list):
			return

		preferences.update(tset("value", message), condition)

		await interaction.response.send_message(f"Set message to `{message}`.", ephemeral=True)

	@app_commands.checks.has_permissions(ban_members=True)
	@app_commands.describe(limit="The maximum reference character limit.")
	@_set.command(description="Set the maximum amount of characters a single reference can call.")
	async def reference_character_limit(self, interaction: discord.Interaction, limit: int):
		assert(interaction.guild)

		preferences = await self.bot.get_guild_preferences(interaction.guild)

		query = Query()
		condition = query.key == "maximum_reference_character_limit"

		pref = preferences.get(condition)
		if not pref or isinstance(pref, list):
			return

		preferences.update(tset("value", limit), condition)

		await interaction.response.send_message(f"Set limit to `{limit}`.", ephemeral=True)

async def setup(bot: SDWB2):
	await bot.add_cog(PrefCog(bot))