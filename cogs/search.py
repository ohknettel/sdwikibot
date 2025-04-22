import discord, typing
from discord.ext.commands import Cog

from bot import SDWikiBot
from constants import EmbedPaginatorView, neutral_colour, wiki_colour, archives_colour
from utils import chunk_list

class SearchCog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot

	@discord.app_commands.describe(
		query="What you are searching for.",
		site="Which site you want to search on. By default, searches on both wiki and archives.",
		where="Whether to search in text or in titles only. By default, searches in titles."
	)
	@discord.app_commands.choices(
		site=[
			discord.app_commands.Choice(name="SimDemocracy Wiki (simdemocracy.miraheze.org)", value="wiki"),
			discord.app_commands.Choice(name="Archives (qwrky.dev)", value="archives")
		],
		where=[
			discord.app_commands.Choice(name="In titles", value="title"),
			discord.app_commands.Choice(name="In text", value="text")
		]
	)
	@discord.app_commands.command(description="Search for a page.")
	async def search(self, interaction: discord.Interaction, query: str, site: typing.Optional[str] = "both", where: typing.Optional[str] = "title"):
		await interaction.response.defer(thinking=True)

		global_embed_colour = neutral_colour if site == "both" else (wiki_colour if site == "wiki" else archives_colour)
		lscreen = discord.Embed(
			colour=global_embed_colour,
			title=f"\N{left-pointing magnifying glass} Search: `{query}`",
			description="Please be patient while I fetch results..."
		).set_author(name="Loading")
		lmsg = await interaction.followup.send(embed=lscreen, wait=True)

		props = {
			"generator": "search",
			"gsrsearch": query,
			"gsrwhat": where,
			"prop": "info",
			"inprop": "url",
			"gsrlimit": 50
		}

		results = []
		if site == "both":
			props["gsrlimit"] = 25

			results = []
			wiki_results = self.bot.sites.wiki.get("query", **props)
			archives_results = self.bot.sites.archives.get("query", **props)

			if (wiki_pages := wiki_results["query"].get("pages")) is not None:
				results += list(wiki_pages.values())

			if (archives_pages := archives_results["query"].get("pages")) is not None:
				results += list(archives_pages.values())
			
		else:
			_site = self.bot.sites.wiki if site == "wiki" else self.bot.sites.archives
			site_results = _site.get("query", **props)
			if (site_pages := site_results["query"].get("pages")) is not None:
				results = list(site_pages.values())

		formatted = []
		for result in results:
			title = result["title"]
			url = result["fullurl"]
			hyperlink = f"[{title}]({url})"

			dup_titles = [index for index, r in enumerate(results) if r["title"] == title]
			if len(dup_titles) > 1:
				other_res = results.pop(max(dup_titles))
				other_url = other_res["fullurl"]
				other_site_name = "wiki" if "simdemocracy.miraheze.org" in other_url else "archives"
				site_name = "wiki" if "simdemocracy.miraheze.org" in url else "archives"
				hyperlink = f"{title} ([{site_name}]({url}), [{other_site_name}]({other_url}))"

			formatted.append(hyperlink)

		if len(formatted) > 0:
			chunks = chunk_list(formatted, 10)
			embeds = []
			for index, chunk in enumerate(chunks, start=1):
				embed = lscreen.copy().set_author(name="" if site == "both" else (site or "").title()).set_footer(text=f"Page ({index}/{len(chunks)})")
				embed.description = "\n".join(f"- {hyperlink}" for hyperlink in chunk)
				embeds.append(embed)

			if len(embeds) > 1:
				paginator = EmbedPaginatorView(interaction.user)
				paginator.items = embeds
				await lmsg.edit(embed=embeds[0], view=paginator)
			else:
				await lmsg.edit(embed=embeds[0])
		else:
			lscreen.set_author(name="").description = "**`No results found.`**"
			await lmsg.edit(embed=lscreen)

async def setup(bot: SDWikiBot):
	await bot.add_cog(SearchCog(bot));