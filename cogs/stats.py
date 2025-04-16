import datetime
import time
import discord

from discord.ext.commands import Cog
from bot import SDWikiBot
from constants import simdem_navy_blue_colour

class StatsCog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot

	def format_bytes(self, size: float):
		power = 1024
		n = 0
		units = ["B", "KB", "MB", "GB"]
		while size > power and n < len(units) - 1:
			size /= power
			n += 1
		return f"{size:.2f} {units[n]}"

	group = discord.app_commands.Group(
		name="stats",
		description="Gather info about various wiki stats."
	)

	@group.command(description="Displays statistics about the wiki.")
	async def wiki(self, interaction: discord.Interaction):
		await interaction.response.defer()

		# Sync API call
		siteinfo = self.bot.site.api(
			"query", "GET", meta="siteinfo", siprop="statistics"
		)
		statistics = siteinfo["query"]["statistics"]

		embed = discord.Embed(
			colour=simdem_navy_blue_colour,
			title="\N{bar chart} Wiki Statistics"
		)
		embed.add_field(name="Pages", value=str(statistics["articles"]), inline=False)
		embed.add_field(name="Edits", value=str(statistics["edits"]), inline=False)
		embed.add_field(name="Images", value=str(statistics["images"]), inline=False)
		embed.add_field(name="Users", value=str(statistics["users"]), inline=False)
		embed.add_field(name="Active Users", value=str(statistics["activeusers"]), inline=False)
		embed.add_field(name="Admins", value=str(statistics["admins"]), inline=False)

		await interaction.followup.send(embed=embed)

	@group.command(name="bot", description="Displays statistics about the bot.")
	async def _bot(self, interaction: discord.Interaction):
		await interaction.response.defer()

		uptime = datetime.timedelta(seconds=int(round(time.time() - self.bot.start_time)))
		discordpy_version = discord.__version__
		commands = len(self.bot.tree.get_commands(type=discord.AppCommandType.chat_input))
		current, heap = self.bot.tm.get_traced_memory()

		embed = discord.Embed(
			colour=simdem_navy_blue_colour,
			title="\N{bar chart} Bot Statistics"
		)
		embed.add_field(name="Uptime", value=f"`{uptime}`", inline=False)
		embed.add_field(name="Discord.py Version", value=f"`{discordpy_version}`", inline=False)
		embed.add_field(name="Commands", value=str(commands))
		embed.add_field(name="Allocated Memory", value=self.format_bytes(current), inline=False)
		embed.add_field(name="Memory Heap", value=self.format_bytes(heap))

		await interaction.followup.send(embed=embed)

	async def cog_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
		if not interaction.response.is_done():
			await interaction.response.defer()

		embed = discord.Embed(
			colour=discord.Colour.red(),
			title=f":x: An error occurred",
			description=f"```{error}```"
		)

		await interaction.followup.send(embed=embed)

async def setup(bot: SDWikiBot):
	await bot.add_cog(StatsCog(bot))
