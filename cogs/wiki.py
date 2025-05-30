import discord, typing, time, asyncio;
from sentence_splitter import split_text_into_sentences;
from discord.ext.commands import Cog;
from datetime import datetime;
from bot import SDWikiBot;
from constants import neutral_colour, wiki_colour, archives_colour;

class SelectionView(discord.ui.View):
	event = asyncio.Event();
	location: str = "";

	def __init__(self):
		super().__init__(timeout=None);

	@discord.ui.button(label="Wiki", style=discord.ButtonStyle.gray)
	async def wiki(self, interaction: discord.Interaction, _):
		await interaction.response.defer();
		self.location = "wiki"
		self.event.set();

	@discord.ui.button(label="Archives", style=discord.ButtonStyle.gray)
	async def archives(self, interaction: discord.Interaction, _):
		await interaction.response.defer();
		self.location = "archives";
		self.event.set();

	async def get_location(self):
		await self.event.wait();
		return self.location;

class WikiCog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot;

	@discord.app_commands.describe(page="The page you wish to view information for.")
	@discord.app_commands.command(description="View information about a page.")
	async def pageinfo(self, interaction: discord.Interaction, page: str):
		await interaction.response.defer(thinking=True);

		lscreen = discord.Embed(
			colour=neutral_colour,
			title=f":information_source: Page Info: `{page}`",
			description="Please be patient while I search for that page..."
		).set_author(name="Loading");
		lmsg = await interaction.followup.send(embed=lscreen, wait=True);

		wiki_page = self.bot.sites.wiki.pages.get(page);
		archives_page = self.bot.sites.archives.pages.get(page);

		if not wiki_page and not archives_page:
			lscreen.set_author(name="").description = "**`No results found.`**";
			await lmsg.edit(embed=lscreen);
			return;

		if all(getattr(page, "pageid") is not None for page in [wiki_page, archives_page]):
			lscreen.set_author(name="").description = "This page exists in both the wiki and archives. For which page do you want to view information?";
			selection_view = SelectionView();
			await lmsg.edit(embed=lscreen, view=selection_view);
			
			loc = await selection_view.get_location();
			if loc == "wiki":
				site = self.bot.sites.wiki;
				_page = wiki_page;
			else:
				site = self.bot.sites.archives;
				_page = archives_page;
		else:
			_page = wiki_page if wiki_page.pageid not in ["", None] else archives_page;
			if _page.pageid in ["", None]:
				lscreen.set_author(name="").description = "**`This page does not exist.`**";
				await lmsg.edit(embed=lscreen);
				return;

			site = self.bot.sites.wiki if _page == wiki_page else self.bot.sites.archives;

		latest_revisions: typing.Any = list(_page.revisions(max_items=1));
		oldest_revisions: typing.Any = list(_page.revisions(max_items=1, dir="newer"));

		if len(latest_revisions) > 0:
			latest_revision = latest_revisions[0];

			_id = latest_revision["revid"];
			user = latest_revision["user"];
			comment = latest_revision["comment"] or "**`No comment.`**";
			timestamp = int(time.mktime(latest_revision["timestamp"]));
			url = f"https://{site.host}{site.path}index.php?diff={_id}";
			
			lscreen.add_field(name="Latest edit", value=f"[`{_id}` - _{comment[:200] + '...' if len(comment) > 200 else comment}_ by **{user}**]({url})\n<t:{timestamp}:R>", inline=False); 

		if len(oldest_revisions) > 0:
			oldest_revision = oldest_revisions[0];

			creation_timestamp = time.mktime(oldest_revision["timestamp"]);
			creation_readable = datetime.fromtimestamp(creation_timestamp).strftime("%B %d, %Y at %I:%M %p");
			created_by = oldest_revision["user"];
			
			lscreen \
				.add_field(name="Creation date", value=f"{creation_readable}\n<t:{int(creation_timestamp)}:R>", inline=False) \
				.add_field(name="Created by", value=created_by);

		extract = site.get("query", prop="extracts", exintro="", explaintext="", titles=_page.name) \
					.get("query", {}) \
					.get("pages", {}) \
					.get(str(_page.pageid), {}) \
					.get("extract", None);

		lscreen.description = "";
		if extract:
			sentences = split_text_into_sentences(extract, language="en");
			for sentence in sentences:
				if len(lscreen.description) < 500:
					lscreen.description += " " + sentence;
				else:
					break;

		lscreen.set_author(name=("wiki" if site == self.bot.sites.wiki else "archives").title());
		lscreen.colour = wiki_colour if site == self.bot.sites.wiki else archives_colour;

		await lmsg.edit(embed=lscreen, view=None);
		
async def setup(bot: SDWikiBot):
	await bot.add_cog(WikiCog(bot));