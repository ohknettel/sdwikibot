import discord
from discord.ext.commands import Cog
from functools import lru_cache
from bot import SDWikiBot
from constants import simdem_navy_blue_colour, EmbedPaginatorView
from utils import chunk_list


class LeaderboardsCog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot

	def get_user_contribs(self, username):
		total = 0
		resp = self.bot.site.get("query", list="usercontribs", ucuser=username, uclimit="max")
		while True:
			total += len(resp["query"]["usercontribs"])
			if "continue" in resp:
				_continue = resp["continue"]["uccontinue"]
				resp = self.bot.site.get("query", list="usercontribs", ucuser=username, uclimit="max", uccontinue=_continue)
			else:
				break
		return total

	@lru_cache(maxsize=None)
	def get_users(self):
		users = []
		resp = self.bot.site.get("query", list="allusers", aulimit="max")
		while True:
			users += [user["name"] for user in resp["query"]["allusers"]]
			if "continue" in resp:
				resp = self.bot.site.get("query", list="allusers", aulimit="max", **resp["continue"])
			else:
				break
		return users

	@lru_cache(maxsize=None)
	def get_page_urls(self):
		results = {}
		resp = self.bot.site.get("query", generator="allpages", prop="info", inprop="url", gaplimit="max")
		while True:
			for page in resp["query"]["pages"].values():
				results[page["title"]] = page["fullurl"]
			if "continue" in resp:
				resp = self.bot.site.get("query", generator="allpages", prop="info", inprop="url", gaplimit="max", **resp["continue"])
			else:
				break
		return results

	async def interaction_check(self, _: discord.Interaction) -> bool:
		self.page_urls = self.get_page_urls()
		return True

	def build_leaderboard_embed(self, user, title, data, fmt_row, page_urls=None):
		chunks = chunk_list(data, 10)
		paginator = EmbedPaginatorView(user)
		for index, chunk in enumerate(chunks):
			embed = discord.Embed(
				colour=simdem_navy_blue_colour,
				title=f"\N{trophy} {title}",
				description=""
			).set_footer(text=f"Page ({index + 1}/{len(chunks)})")

			for rank, row in enumerate(chunk):
				emoji = {
					0: "\N{first place medal}",
					1: "\N{second place medal}",
					2: "\N{third place medal}"
				}.get(rank if index == 0 else -1, "-")

				embed.description += "\n" + fmt_row(rank, row, emoji, page_urls)

			paginator.add_embed(embed)
		return paginator

	leaderboards = discord.app_commands.Group(name="leaderboard", description="View the leaderboards for different wiki statistics.")

	@leaderboards.command(description="View the user contributions leaderboard.")
	async def contribs(self, interaction: discord.Interaction):
		await interaction.response.defer(thinking=True)
		users = self.get_users()
		edit_counts = [(user, self.get_user_contribs(user)) for user in users]
		leaderboard = sorted(edit_counts, key=lambda x: x[1], reverse=True)[:50]

		paginator = self.build_leaderboard_embed(
			interaction.user,
			"Leaderboard: User Contributions",
			leaderboard,
			lambda _, row, emoji, __: f"{emoji} **{row[0]}** ~ `{row[1]}` edits"
		)

		if len(paginator.items) <= 1:
			await interaction.followup.send(embed=paginator.items[0])
		else:
			await interaction.followup.send(embed=paginator.items[0], view=paginator)

	@leaderboards.command(description="View the page length leaderboard.")
	async def pagelength(self, interaction: discord.Interaction):
		await interaction.response.defer(thinking=True)
		edit_counts = [(page.page_title, page.length) for page in self.bot.site.pages]
		leaderboard = sorted(edit_counts, key=lambda x: x[1], reverse=True)[:50]

		def format_pagelength(_, row, emoji, urls):
			title, length = row
			if urls and title in urls:
				return f"{emoji} **[{title}]({urls[title]})** ~ `{length}` bytes"
			return f"{emoji} **{title}** ~ `{length}` bytes"

		paginator = self.build_leaderboard_embed(
			interaction.user,
			"Leaderboard: Page Length",
			leaderboard,
			format_pagelength,
			self.page_urls
		)

		if len(paginator.items) <= 1:
			await interaction.followup.send(embed=paginator.items[0])
		else:
			await interaction.followup.send(embed=paginator.items[0], view=paginator)

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
	await bot.add_cog(LeaderboardsCog(bot))
