from tinydb import Query
from tinydb.operations import set as tset
from bot import SDWB2
from discord.ext import commands
import discord
import textwrap
import typing

async def host_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
    hostnames = [h["name"] for h in typing.cast(SDWB2, interaction.client).hosts]
    return [discord.app_commands.Choice(name=option, value=option) for option in hostnames if option.lower().startswith(current.lower())][:25]

class HostsCog(commands.Cog):
	def __init__(self, bot: SDWB2):
		self.bot = bot

	@commands.hybrid_group(name="hosts", description="Configure SD Wikibot's hosts.")
	async def group(self, _: commands.Context):
		pass

	@group.command(name="list", description="Lists the wiki hosts SD Wikibot retrieves information from.")
	async def _list(self, ctx: commands.Context):
		assert(ctx.guild)

		hosts = self.bot.hosts
		emojis = self.bot.get_emojis(ctx.guild)

		message = ""

		for host in hosts:
			message += textwrap.dedent(f"""`{host["name"]}` *({host["main_url"]})*
{emojis.toggle_on if host["enabled"] else emojis.toggle_off} {"Enabled" if host["enabled"] else "Disabled"}\n\n""")

		await ctx.reply(message.strip())

	@commands.is_owner()
	@discord.app_commands.checks.has_permissions(administrator=True)
	@discord.app_commands.describe(hostname="The name of the host.", main_url="The URL of the main page of the host.", api_url="The API endpoint URL of the host.")
	@group.command(name="add", description="Adds a new host.")
	async def add(self, ctx: commands.Context, hostname: str, main_url: str, api_url: str):
		assert(ctx.guild)

		hosts = self.bot.hosts
		query = Query()

		if hosts.contains(query.name == hostname):
			return await ctx.reply(f"Host `{hostname}` already exists!", ephemeral=True)

		hosts.insert({ "name": hostname, "main_url": main_url, "api_url": api_url, "enabled": True })

		await ctx.reply(f"Added host `{hostname}`.", ephemeral=True)

	@commands.is_owner()
	@discord.app_commands.checks.has_permissions(administrator=True)
	@discord.app_commands.autocomplete(hostname=host_autocomplete)
	@discord.app_commands.describe(hostname="The name of the host.")
	@group.command(name="remove", description="Removes a host.")
	async def remove(self, ctx: commands.Context, hostname: str):
		assert(ctx.guild)

		hosts = self.bot.hosts
		query = Query()
		emojis = self.bot.get_emojis(ctx.guild)

		if not hosts.contains(query.name == hostname):
			return await ctx.reply(f"Host `{hostname}` does not exist!", ephemeral=True)

		hosts.remove(query.name == hostname)

		await ctx.reply(f"Enabled host `{hostname}` {emojis.toggle_on}.", ephemeral=True)

	@commands.is_owner()
	@discord.app_commands.checks.has_permissions(administrator=True)
	@discord.app_commands.autocomplete(hostname=host_autocomplete)
	@discord.app_commands.describe(hostname="The name of the host.")
	@group.command(name="enable", description="Enables a host.")
	async def enable(self, ctx: commands.Context, hostname: str):
		assert(ctx.guild)

		hosts = self.bot.hosts
		query = Query()
		emojis = self.bot.get_emojis(ctx.guild)

		if not hosts.contains(query.name == hostname):
			return await ctx.reply(f"Host `{hostname}` does not exist!", ephemeral=True)

		hosts.update(tset("enabled", True), query.name == hostname)

		await ctx.reply(f"Enabled host `{hostname}` {emojis.toggle_on}.", ephemeral=True)

	@commands.is_owner()
	@discord.app_commands.checks.has_permissions(administrator=True)
	@discord.app_commands.autocomplete(hostname=host_autocomplete)
	@discord.app_commands.describe(hostname="The name of the host.")
	@group.command(name="disable", description="Disables a host.")
	async def disable(self, ctx: commands.Context, hostname: str):
		assert(ctx.guild)

		hosts = self.bot.hosts
		query = Query()
		emojis = self.bot.get_emojis(ctx.guild)

		if not hosts.contains(query.name == hostname):
			return await ctx.reply(f"Host `{hostname}` does not exist!", ephemeral=True)

		hosts.update(tset("enabled", False), query.name == hostname)

		await ctx.reply(f"Disabled host `{hostname}` {emojis.toggle_off}.", ephemeral=True)

async def setup(bot: SDWB2):
	await bot.add_cog(HostsCog(bot))