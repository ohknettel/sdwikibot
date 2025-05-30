import time, discord, typing;
from discord.ext.commands import Cog;
from collections import Counter;
from bot import SDWikiBot;
from constants import EmbedPaginatorView, wiki_colour, archives_colour;
from utils import chunk_list;

class LeaderboardsCog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot;
		self.cache: dict[str, tuple] = {};

		self.cache_duration = 300; # seconds

	def is_cache_expired(self, key: str):
		_, timestamp = self.cache.get(key, ([], 0));
		return (time.time() - timestamp) > self.cache_duration;

	def update_cache(self, key: str, value):
		self.cache[key] = (value, time.time());

	def get_rc_leaderboards(self, site: typing.Union[str, typing.Literal["wiki", "archives"]] = "wiki", limit=50):
		edits, new_pages = Counter(), Counter();
		_site = self.bot.sites.wiki if site == "wiki" else self.bot.sites.archives;
		params = {
			"list": "recentchanges",
			"rcprop": "title|user|timestamp",
			"rclimit": "max"
		};

		while True:
			resp = _site.get("query", **params);
			changes = resp.get("query", {}).get("recentchanges", []);

			for change in changes:
				if not isinstance(change, typing.OrderedDict):
					continue;

				if "user" in change and "type" in change:
					if change["type"] == "edit":
						edits[change["user"]] += 1;
					elif change["type"] == "new":
						new_pages[change["user"]] += 1;

			if (cont := resp.get("continue")) is not None:
				params.update(cont);
			else:
				break;

		return (edits.most_common(limit), new_pages.most_common(limit));

	def get_contribs_leaderboard(self, site: typing.Union[str, typing.Literal["wiki", "archives"]] = "wiki", limit=50):
		contribs = Counter();
		_site = self.bot.sites.wiki if site == "wiki" else self.bot.sites.archives
		params = {
			"list": "allusers",
			"aulimit": "max"
		}

		while True:
			resp = _site.get("query", **params);
			users = resp.get("query", {}).get("allusers", []);

			for user in users:
				cparams = {
					"list": "usercontribs",
					"ucuser": user["name"],
					"uclimit": "max"
				}

				while True:
					cresp = _site.get("query", **cparams);
					ucontribs = len(cresp.get("query", {}).get("usercontribs", []));
					if ucontribs > 0:
						contribs[user["name"]] += ucontribs

					if (cont := cresp.get("continue")) is not None:
						cparams.update(cont);
					else:
						break;

			if (cont := resp.get("continue")) is not None:
				params.update(cont);
			else:
				break;

		return contribs.most_common(limit);


	leaderboards = discord.app_commands.Group(name="leaderboards", description="View leaderboards for wiki and archives.");

	@discord.app_commands.describe(
		site="Which site you want to search on. By default, displays leaderboard for wiki.",
	)
	@discord.app_commands.choices(
		site=[
			discord.app_commands.Choice(name="SimDemocracy Wiki (simdemocracy.miraheze.org)", value="wiki"),
			discord.app_commands.Choice(name="Archives (qwrky.dev)", value="archives")
		]
	)
	@leaderboards.command(description="View the leaderboard for most edits.")
	async def edits(self, interaction: discord.Interaction, site: str = "wiki"):
		await interaction.response.defer(thinking=True);

		lscreen = discord.Embed(
			colour=wiki_colour if site == "wiki" else archives_colour,
			title=f":trophy: **Leaderboards:** Edits",
			description="Please be patient while I organize the leaderboard..."
		).set_author(name="Loading");
		lmsg = await interaction.followup.send(embed=lscreen, wait=True);

		if self.is_cache_expired(f"edits_leaderboard_{site}"):
			data, new_pages = self.get_rc_leaderboards(site);
			self.update_cache(f"edits_leaderboard_{site}", data);
			self.update_cache(f"new_pages_leaderboard_{site}", new_pages);
		else:
			data, _ = self.cache[f"edits_leaderboard_{site}"];
		chunks = chunk_list(data, 10);
		embeds = [];
		for index, chunk in enumerate(chunks, start=1):
			embed = lscreen.copy().set_author(name=(site or "").title()).set_footer(text=f"Page ({index}/{len(chunks)})");
			
			emoji = {
				0: ":first_place:",
				1: ":second_place:",
				2: ":third_place:"
			};

			embed.description = "\n".join(emoji.get(rank if index == 1 else -1, "-") + f" **{user}**: `{edits}` edit(s)" for rank, (user, edits) in enumerate(chunk));
			embeds.append(embed);

		if len(embeds) > 1:
			paginator = EmbedPaginatorView(interaction.user);
			paginator.items = embeds
			await lmsg.edit(embed=embeds[0], view=paginator);
		else:
			await lmsg.edit(embed=embeds[0]);

	@discord.app_commands.describe(
		site="Which site you want to search on. By default, displays leaderboard for wiki.",
	)
	@discord.app_commands.choices(
		site=[
			discord.app_commands.Choice(name="SimDemocracy Wiki (simdemocracy.miraheze.org)", value="wiki"),
			discord.app_commands.Choice(name="Archives (qwrky.dev)", value="archives")
		]
	)
	@leaderboards.command(description="View the leaderboard for most new pages created.")
	async def new_pages(self, interaction: discord.Interaction, site: str = "wiki"):
		await interaction.response.defer(thinking=True);

		lscreen = discord.Embed(
			colour=wiki_colour if site == "wiki" else archives_colour,
			title=f":trophy: **Leaderboards:** New Pages",
			description="Please be patient while I organize the leaderboard..."
		).set_author(name="Loading");
		lmsg = await interaction.followup.send(embed=lscreen, wait=True);

		if self.is_cache_expired(f"edits_leaderboard_{site}"):
			edits, data = self.get_rc_leaderboards(site);
			self.update_cache(f"edits_leaderboard_{site}", edits);
			self.update_cache(f"new_pages_leaderboard_{site}", data);
		else:
			data, _ = self.cache[f"new_pages_leaderboard_{site}"];

		chunks = chunk_list(data, 10);
		embeds = [];
		for index, chunk in enumerate(chunks, start=1):
			embed = lscreen.copy().set_author(name=(site or "").title()).set_footer(text=f"Page ({index}/{len(chunks)})");
			
			emoji = {
				0: ":first_place:",
				1: ":second_place:",
				2: ":third_place:"
			};

			embed.description = "\n".join(emoji.get(rank if index == 1 else -1, "-") + f" **{user}**: `{edits}` page(s)" for rank, (user, edits) in enumerate(chunk));
			embeds.append(embed);

		if len(embeds) > 1:
			paginator = EmbedPaginatorView(interaction.user);
			paginator.items = embeds;
			await lmsg.edit(embed=embeds[0], view=paginator);
		else:
			await lmsg.edit(embed=embeds[0]);

	@discord.app_commands.describe(
		site="Which site you want to search on. By default, displays leaderboard for wiki.",
	)
	@discord.app_commands.choices(
		site=[
			discord.app_commands.Choice(name="SimDemocracy Wiki (simdemocracy.miraheze.org)", value="wiki"),
			discord.app_commands.Choice(name="Archives (qwrky.dev)", value="archives")
		]
	)
	@leaderboards.command(description="View the leaderboard for most contributions made.")
	async def contribs(self, interaction: discord.Interaction, site: str = "wiki"):
		await interaction.response.defer(thinking=True);

		lscreen = discord.Embed(
			colour=wiki_colour if site == "wiki" else archives_colour,
			title=f":trophy: **Leaderboards:** Contributions",
			description="Please be patient while I organize the leaderboard..."
		).set_author(name="Loading");
		lmsg = await interaction.followup.send(embed=lscreen, wait=True);

		if self.is_cache_expired(f"contribs_leaderboard_{site}"):
			data = self.get_contribs_leaderboard(site);
			self.update_cache(f"contribs_leaderboard_{site}", data);
		else:
			data, _ = self.cache[f"contribs_leaderboard_{site}"];
		chunks = chunk_list(data, 10);
		embeds = [];
		for index, chunk in enumerate(chunks, start=1):
			embed = lscreen.copy().set_author(name=(site or "").title()).set_footer(text=f"Page ({index}/{len(chunks)})");
			
			emoji = {
				0: ":first_place:",
				1: ":second_place:",
				2: ":third_place:"
			};

			embed.description = "\n".join(emoji.get(rank if index == 1 else -1, "-") + f" **{user}**: `{edits}` contribution(s)" for rank, (user, edits) in enumerate(chunk));
			embeds.append(embed);

		if len(embeds) > 1:
			paginator = EmbedPaginatorView(interaction.user);
			paginator.items = embeds;
			await lmsg.edit(embed=embeds[0], view=paginator);
		else:
			await lmsg.edit(embed=embeds[0]);

async def setup(bot: SDWikiBot):
	await bot.add_cog(LeaderboardsCog(bot));