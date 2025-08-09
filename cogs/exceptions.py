from bot import SDWB2
from discord.ext.commands import Cog
import discord
import traceback
import os

class ExceptionsCog(Cog):
	def __init__(self, bot: SDWB2):
		self.bot = bot
		self.bot.tree.error(self.__dispatch_to_app_command_handler)

	async def __dispatch_to_app_command_handler(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
		self.bot.dispatch("app_command_error", interaction, error)

	@Cog.listener("on_app_command_error")
	async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
		if isinstance(error, discord.app_commands.MissingPermissions):
			embed = discord.Embed(
				description=f"You are not authorized to run this command.",
				colour=discord.Colour.red()
			)

			await interaction.response.send_message(embed=embed, ephemeral=True)
		else:
			error_data = "".join(traceback.format_exception(type(error), error, error.__traceback__))
			error_data.replace(os.getenv("USERNAME", ""), "...")

			embed = discord.Embed(
				description=f"{error}\n```fix\n{error_data}```",
				colour=discord.Colour.red()
			)

			await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: SDWB2):
	await bot.add_cog(ExceptionsCog(bot))