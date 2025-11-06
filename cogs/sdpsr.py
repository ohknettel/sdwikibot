import traceback
from bot import SDWB2
from discord.ext import commands, tasks
from discord import app_commands
from functools import lru_cache
from precedents import PrecedentSearch, chunkify, SearchResult
from dateutil.parser import parse
from typing import cast
import discord

@lru_cache()
async def get_jurisdictions(conn):
	cur = await conn.execute("""
		SELECT DISTINCT jurisdiction FROM case_info
	""")
	return [r[0] for r in await cur.fetchall()]

async def juris_autocomplete(interaction: discord.Interaction, current: str):
	client: SDWB2 = cast(SDWB2, interaction.client)
	jurisdictions: list[str] = await get_jurisdictions(client.db)
	return [app_commands.Choice(name=jur, value=jur) for jur in jurisdictions if current.strip().lower() in jur.lower()]

class NonsearchPrecedentsView(discord.ui.LayoutView):
	container = discord.ui.Container(
		discord.ui.Section(
			discord.ui.TextDisplay(content="# SimDemocracy Precedent Search"),
			discord.ui.TextDisplay(content="```...```", id=2009),
			accessory=discord.ui.Thumbnail(
				media="",
			),
			id=11405
		),
		discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
		accent_colour=0x163248,
	)

	def set_query(self, query: str):
		item = self.container.find_item(2009)
		if item and isinstance(item, discord.ui.TextDisplay):
			item.content = f"```{query}```"

	def add_text(self, text: str):
		self.container.add_item(discord.ui.TextDisplay(content=text))

	def set_image(self, file: discord.File):
		item = self.container.find_item(11405)
		if item and isinstance(item, discord.ui.Section) and isinstance(item.accessory, discord.ui.Thumbnail):
			item.accessory.media = file
 
class PrecedentsView(NonsearchPrecedentsView):
	def __init__(self, interaction: discord.Interaction, chunks: list[list[SearchResult]]):
		super().__init__()
		self.interaction = interaction
		self.chunks = chunks
		self.total = len(chunks)
		self.index = 0
		self.base_size = len(self.container.children)

		if self.total in [0, 1]:
			for button in [self._first, self._last, self._next, self._prev]:
				button.disabled = True
		else:
			self.toggle_buttons()

		if self.total > 0:
			self.populate_view(self.index)
		
		self._page.label = f"{self.index + 1}/{self.total}"

	action_row = discord.ui.ActionRow()

	async def on_timeout(self):
		for i in self.walk_children():
			if isinstance(i, discord.ui.Section) and isinstance(i.accessory, discord.ui.Button):
				i.accessory.disabled = True
			elif isinstance(i, discord.ui.ActionRow):
				for child in i.walk_children():
					if isinstance(child, discord.ui.Button):
						child.disabled = True

		await self.interaction.edit_original_response(view=self)

	def populate_view(self, new_index: int):
		section = self.container.find_item(11405)
		if not section or not isinstance(section, discord.ui.Section):
			return

		children = self.container.children
		self.container.clear_items()

		for child in children[:self.base_size]:
			self.container.add_item(child)

		for result in self.chunks[new_index]:
			data = result["data"]
			self.container.add_item(discord.ui.TextDisplay(
				content=f"> {data[2]}\n[{data[0]}]({data[1]})"
			))

	def toggle_buttons(self):
		self._first.disabled = self.index == 0
		self._prev.disabled = self.index == 0

		self._next.disabled = self.index >= self.total - 1
		self._last.disabled = self.index >= self.total - 1

		self._page.label = f"{self.index + 1}/{self.total}"

	async def populate_and_edit(self):
		try:
			self.toggle_buttons()
			self.populate_view(self.index)
			await self.interaction.edit_original_response(view=self)
		except Exception:
			traceback.print_exc()
	
	@action_row.button(emoji="⏪", style=discord.ButtonStyle.blurple)
	async def _first(self, interaction: discord.Interaction, _):
		await interaction.response.defer(ephemeral=True)
		if interaction.user != self.interaction.user:
			return await interaction.followup.send(content=f"Run this command for yourself, please!", ephemeral=True)

		self.index = 0
		await self.populate_and_edit()

	@action_row.button(emoji="◀", style=discord.ButtonStyle.blurple)
	async def _prev(self, interaction: discord.Interaction, _):
		await interaction.response.defer(ephemeral=True)
		if interaction.user != self.interaction.user:
			return await interaction.followup.send(content=f"Run this command for yourself, please!", ephemeral=True)

		self.index = max(0, self.index - 1)
		await self.populate_and_edit()

	@action_row.button(label="0/0", disabled=True)
	async def _page(self, __interaction__: discord.Interaction, _):
		pass

	@action_row.button(emoji="▶", style=discord.ButtonStyle.blurple)
	async def _next(self, interaction: discord.Interaction, _):
		await interaction.response.defer(ephemeral=True)
		if interaction.user != self.interaction.user:
			return await interaction.followup.send(content=f"Run this command for yourself, please!", ephemeral=True)

		self.index = min(self.index + 1, self.total - 1)
		await self.populate_and_edit()

	@action_row.button(emoji="⏩", style=discord.ButtonStyle.blurple)
	async def _last(self, interaction: discord.Interaction, _):
		await interaction.response.defer(ephemeral=True)
		if interaction.user != self.interaction.user:
			return await interaction.followup.send(content=f"Run this command for yourself, please!", ephemeral=True)

		self.index = self.total - 1
		await self.populate_and_edit()

class SDPSR(commands.Cog):
	def __init__(self, bot: SDWB2):
		self.bot = bot

	async def cog_load(self):
		self.searcher = PrecedentSearch(self.bot.db, self.bot.session)
		await self.searcher.load_index()
		self.fetch_cases.start()

	@tasks.loop(hours=6)
	async def fetch_cases(self):
		await self.searcher.reload_index()

	@app_commands.checks.cooldown(2, 8)
	@app_commands.command(description="Search the SimDemocracy law precedent database.")
	@app_commands.describe(
		query="The precedent or topic you are searching for.",
		jurisdiction="Which court issued the precedent.",
		before="To filter out precedent from cases before this date.",
		after="To filter out precedent from cases after this date.",
		has_judge="To filter out precedent from cases which have this judge/justice/etc. (use commas to specify >1).")
	@app_commands.autocomplete(jurisdiction=juris_autocomplete)
	async def precedent(self, interaction: discord.Interaction, query: str,
								jurisdiction: str | None = None,
								before: str | None = None,
								after: str | None = None,
								has_judge: str | None = None):
		await interaction.response.defer(thinking=True)

		file = discord.File("./assets/sd.png")
		view = NonsearchPrecedentsView()

		view.set_query(query)
		view.set_image(file)
		view.add_text("<a:loading:1425892090163761223>  Please wait while results are being fetched...")
		await interaction.followup.send(view=view, file=file)

		try:
			try:
				before_dt = parse(before) if before else None
				after_dt = parse(after) if after else None
			except Exception:
				before_dt = None
				after_dt = None

			file = discord.File("./assets/sd.png")
			results = await self.searcher.search(query, jurisdiction=jurisdiction, before=before_dt, after=after_dt, has_judge=has_judge)

			if len(results) <= 0:
				view = PrecedentsView(interaction, [])
				view.add_text("No results found.")
			else:
				chunks = chunkify(results, 6)
				view = PrecedentsView(interaction, list(chunks))
			
			view.set_query(query)
			view.set_image(file)

			return await interaction.edit_original_response(content=None, view=view, attachments=[file])
		except Exception:
			traceback.print_exc()

async def setup(bot: SDWB2):
	# await bot.add_cog(SDPSR(bot))
	return