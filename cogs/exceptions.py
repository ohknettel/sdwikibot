import discord, traceback
from discord.ext.commands import Cog
from bot import SDWikiBot

class ExceptionsCog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot
		self.bot.tree.error(self.__dispatch_to_app_command_handler)

	async def __dispatch_to_app_command_handler(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
		self.bot.dispatch("app_command_error", interaction, error)

	@Cog.listener("on_app_command_error")
	async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
		if isinstance(error, discord.app_commands.MissingPermissions):
			embed = discord.Embed(
				colour=discord.Colour.red(),
				title=f":x: Unauthorized",
				description=f"You are not authorized to run this command."
			)

			await interaction.response.send_message(embed=embed, ephemeral=True)
		else:
			if not interaction.response.is_done():
				await interaction.response.defer()

			embed = discord.Embed(
				colour=discord.Colour.red(),
				title=f":x: An error occurred",
				description=f"```{error}```"
			)

			await interaction.followup.send(embed=embed)
			traceback.print_exception(None, error, None)

async def setup(bot: SDWikiBot):
	await bot.add_cog(ExceptionsCog(bot));