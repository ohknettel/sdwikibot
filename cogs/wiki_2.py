import discord, typing, time, re
from discord.ext.commands import Cog
from functools import lru_cache
from sentence_splitter import split_text_into_sentences;
from mwclient.listing import Category
from mwclient.page import Page
from bot import SDWikiBot
from constants import simdem_navy_blue_colour

class PageInfoView(discord.ui.View):
	summary_embed: discord.Embed
	history_embed: discord.Embed
	sections_embed: discord.Embed

	def __init__(self, user: typing.Union[discord.User, discord.Member], bot: SDWikiBot, page_url: typing.Optional[str], page_obj: typing.Union[Page, Category]):
		super().__init__()
		self.user = user
		self.bot = bot
		self.page_obj = page_obj
		self.page_url = page_url
		if page_url:
			self.url_button = discord.ui.Button(label="Visit", url=page_url)
			self.add_item(self.url_button)

	def set_message(self, message: discord.WebhookMessage):
		self.message = message

	async def handle_selections(self, custom_id: typing.Optional[str], embed: typing.Optional[discord.Embed] = None):
		for item in self.children:
			if isinstance(item, discord.ui.Button):
				if not item.url:
					item.disabled = item.custom_id == custom_id
					item.style = discord.ButtonStyle.green if item.disabled else discord.ButtonStyle.gray

		await self.message.edit(embed=embed, view=self)

	def get_summary_embed(self):
		if getattr(self, "summary_embed", None) is None:
			extract = self.bot.site.get("query", prop="extracts", exintro="", explaintext="", titles=self.page_obj.base_title)["query"]["pages"][str(self.page_obj.pageid)]["extract"]
			try:
				thumb = self.bot.site.get("query", prop="pageimages", pithumbsize=125, titles=self.page_obj.base_title)["query"]["pages"][str(self.page_obj.pageid)]["thumbnail"]["source"]
			except Exception:
				thumb = None

			embed = discord.Embed(
				colour=simdem_navy_blue_colour,
				title=f":information_source: Page Info: `{self.page_obj.base_title}`",
				description="`Summary could not be fetched.`",
			).set_thumbnail(url=thumb)

			if extract:
				embed.description = ""
				assert(embed.description is not None)
				if (len(embed.description) + len(extract)) > 2000:
					sentences = split_text_into_sentences(extract, language="en")
					for sentence in sentences:
						if (len(sentence) + len(embed.description or "")) < 2000:
							embed.description += " " + sentence
						else:
							break
				else:
					embed.description = extract

			self.summary_embed = embed

		return self.summary_embed

	def get_history_embed(self):
		if getattr(self, "history_embed", None) is None:
			revisions = list(self.page_obj.revisions(max_items=10))
			self.history_embed = discord.Embed(
				colour=simdem_navy_blue_colour,
				title=f":information_source: Page Info: `{self.page_obj.base_title}`",
				description="## Latest 10 items"
			)
			assert(self.history_embed.description)

			for item in revisions:
				if not isinstance(item, typing.OrderedDict):
					continue;

				revid = item.get("revid")
				user = item.get("user")
				timestamp = item.get("timestamp")
				comment = re.sub(r"([*_#])", r"\\\1", item.get("comment", "**`No comment.`**"))

				if revid and user and timestamp:
					self.history_embed.description += f"\n- [`{revid}`] \N{bust in silhouette} **{user}**: {comment} (<t:{int(time.mktime(timestamp))}:R>)"

		return self.history_embed

	def get_sections_embed(self):
		if getattr(self, "sections_embed", None) is None:
			self.sections_embed = discord.Embed(
				colour=simdem_navy_blue_colour,
				title=f":information_source: Page Info: `{self.page_obj.base_title}`",
				description=""
			)
			assert(self.sections_embed.description is not None)

			sections = self.bot.site.get("parse", prop="sections", page=self.page_obj.base_title)["parse"]["sections"]
			sections = typing.cast(typing.OrderedDict, sections);
			for section in list(sections):
				spacing = "\t" * section["toclevel"] if section["toclevel"] != 1 else ""
				anchor = section["anchor"]
				title = anchor.replace("_", " ")
				hyperlink = f"[{title}]({self.page_url}#{anchor})" if self.page_url else title
				self.sections_embed.description += f"\n{spacing}- {hyperlink}"

		return self.sections_embed

	@discord.ui.button(label="Summary", style=discord.ButtonStyle.green, disabled=True, custom_id="summary")
	async def summary(self, interaction: discord.Interaction, button: discord.ui.Button):
		if not interaction.user == self.user:
			await interaction.response.send_message("You are not the executor of this command!", ephemeral=True)
			return;

		await interaction.response.defer()
		await self.handle_selections(button.custom_id, self.get_summary_embed())

	@discord.ui.button(label="History", style=discord.ButtonStyle.gray, custom_id="history")
	async def history(self, interaction: discord.Interaction, button: discord.ui.Button):
		if not interaction.user == self.user:
			await interaction.response.send_message("You are not the executor of this command!", ephemeral=True)
			return;

		await interaction.response.defer()
		await self.handle_selections(button.custom_id, self.get_history_embed())

	@discord.ui.button(label="Sections", style=discord.ButtonStyle.gray, custom_id="sections")
	async def sections(self, interaction: discord.Interaction, button: discord.ui.Button):
		if not interaction.user == self.user:
			await interaction.response.send_message("You are not the executor of this command!", ephemeral=True)
			return;

		await interaction.response.defer()
		await self.handle_selections(button.custom_id, self.get_sections_embed())

class Wiki2Cog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot

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

	@discord.app_commands.command(description="Fetches the main page.")
	async def main(self, interaction: discord.Interaction):
		await interaction.response.defer()

		title = "Main Page"
		url = self.page_urls.get(title)

		logo = self.bot.site.api("query", "GET", meta="siteinfo", siprop="general")["query"]["general"]["logo"]

		embed = discord.Embed(
			colour=simdem_navy_blue_colour,
			title=f"\N{globe with meridians} SimDemocracy Wiki",
			description="The wiki for SimDemocracy — an online experiment governed fully democratically since 2019. Our community is active on [r/SimDemocracy](https://www.reddit.com/r/SimDemocracy/) and [Discord](https://discord.gg/simdemocracy). SimDemocracy operates as a simulated democratic system with an elected government.",
			url=url
		).set_thumbnail(url=logo)
		await interaction.followup.send(embed=embed)

	@discord.app_commands.describe(page="The page you are looking for.")
	
	@discord.app_commands.command(description="Displays information about a page.")
	async def pageinfo(self, interaction: discord.Interaction, page: str):
		await interaction.response.defer(thinking=True)

		titles = list(self.bot.site.search(page, what="title"))
		if not titles:
			embed = discord.Embed(
				colour=simdem_navy_blue_colour,
				title=f":information_source: Page Info: `{page}`",
				description=f"No pages were found matching `{page}`. Please ensure that the page exists."
			)
			await interaction.followup.send(embed=embed)
			return

		title = typing.cast(typing.OrderedDict, titles[0])["title"]
		_page = typing.cast(typing.Union[Page, Category], self.bot.site.pages.get(title))
		url = self.page_urls.get(title)

		pi_view = PageInfoView(user=interaction.user, bot=self.bot, page_url=url, page_obj=_page)
		msg = await interaction.followup.send(view=pi_view, embed=pi_view.get_summary_embed(), wait=True)
		pi_view.set_message(msg)

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
	await bot.add_cog(Wiki2Cog(bot))