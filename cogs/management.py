import discord
import typing

from discord.ext.commands import Cog
from bot import SDWikiBot

async def extension_autocomplete(interaction: discord.Interaction, current: str):
	bot = typing.cast(SDWikiBot, interaction.client)
	extensions = list(bot.extensions.keys())
	options = []

	for ext in extensions:
		if ext.startswith(current):
			options.append(discord.app_commands.Choice(name=ext.split(".")[-1].capitalize(), value=ext))

	return options[:25]

class ManagementCog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot

	@discord.app_commands.command(description="Reloads the specified extension.")
	@discord.app_commands.checks.has_permissions(manage_messages=True)
	@discord.app_commands.autocomplete(extension=extension_autocomplete)
	async def reload(self, interaction: discord.Interaction, extension: str):
		await interaction.response.defer()

		try:
			await self.bot.reload_extension(extension)

			embed = discord.Embed(
				title=":white_check_mark: Reloaded extension successfully",
				description=f"Reloaded extension `{extension}`.",
				colour=discord.Colour.green()
			)

			await interaction.followup.send(embed=embed)

		except Exception as e:
			error_message = (
				f"Reloading `{extension}` failed with the following exception:\n"
				f"```{type(e).__name__}: {e}```"
			)

			embed = discord.Embed(
				title=":x: Failed to reload extension",
				description=error_message,
				colour=discord.Colour.red()
			)

			await interaction.followup.send(embed=embed)

async def setup(bot: SDWikiBot):
	await bot.add_cog(ManagementCog(bot))