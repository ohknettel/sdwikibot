from collections import defaultdict
from discord.ext.commands import Cog
from bot import SDWikiBot
from constants import neutral_colour
from difflib import get_close_matches
import discord, re, types, traceback, textwrap, asyncio

class EventsCog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot
		self.owner = None # prevent calling application info many times

	@Cog.listener()
	async def on_message(self, message: discord.Message):
		if message.author.bot or not message.guild or not self.bot.user:
			return
		settings = types.SimpleNamespace(**self.bot.get_guild_settings(message.guild.id))		

		content = message.content
		if content.strip() in (self.bot.user.mention, f"<@!{self.bot.user.id}>") and settings.help_on_mention:
			try:
				if self.owner is None:
					self.owner = (await self.bot.application_info()).owner

				embed = discord.Embed(
					colour=neutral_colour,
					title=f"Welcome",
					description=textwrap.dedent(f"""
						The **S**im**D**emocracy**Wikibot** is a bot designed to fetch and display pages from both the wiki and archives.

						Browse and search pages, view statistics, display leaderboards and automatically reference pages through smart referencing by using `[[page]]` in your messages.
						
						Wish to start searching? Use `/search` and begin your journey of inquiries.
						Wish to configure the bot? Use `/settings list` to learn about the bot's settings and set them using `/settings set`.

						Want to report a bug or complain about technical difficulties? Please contact {self.owner.mention}.
					""")
				).set_thumbnail(url=self.bot.user.avatar)

				await message.reply(embed=embed)
			except Exception as e:
				traceback.print_exception(type(e), e, e.__traceback__)

		elif settings.toggle_smart_referencing:
			try:
				queries = re.findall(r"\[\[(.+?)\]\]", content)
				if not queries:
					return

				prefix = settings.link_prefix_message if settings.link_prefix_message and settings.link_prefix_message != "None" else ""
				plenary = await message.reply(f"{prefix} Loading...".strip())

				finds = {}
				url_format = "<%s>" if settings.silence_link_embeds else "%s"
				loop = asyncio.get_event_loop()
				props = {
					"generator": "search",
					"gsrwhat": "title",
					"gsrlimit": 25,
					"prop": "info",
					"inprop": "url",
				}

				for query in queries:
					props["gsrsearch"] = query
					try:
						wiki_task = loop.run_in_executor(None, lambda: self.bot.sites.wiki.get("query", **props))
						archives_task = loop.run_in_executor(None, lambda: self.bot.sites.archives.get("query", **props))
						
						wiki_results, archives_results = await asyncio.gather(wiki_task, archives_task)

						results = []
						for result_group in (wiki_results, archives_results):
							pages = result_group.get("query", {}).get("pages", {})
							results.extend(pages.values())

						titles_map = defaultdict(list)
						for result in results:
							titles_map[result["title"]].append(result)

						closest_titles = get_close_matches(query, titles_map.keys(), n=7, cutoff=0.5)
						formatted_links = []
					
						for title in closest_titles:
							entries = titles_map[title]
							if len(entries) == 1:
								result = entries[0]
								url = url_format % result["fullurl"]
								formatted_links.append(f"[`{title}`]({url})")
							else:
								a, b = entries[:2]
								url_a = url_format % a["fullurl"]
								url_b = url_format % b["fullurl"]
								site_a = "wiki" if "simdemocracy.miraheze.org" in url_a else "archives"
								site_b = "wiki" if site_a == "archives" else "archives"
								formatted_links.append(f"`{title} (`[`{site_a}`]({url_a})`, `[`{site_b}`]({url_b})`)`")

						if formatted_links:
							finds[query] = formatted_links

					except Exception as e:
						traceback.print_exception(type(e), e, e.__traceback__)
						continue

				finds = {k: v for k, v in finds.items() if v}
				if not finds:
					return

				find_values = list(finds.values())
				noun = "Links" if len(queries) > 1 else "Link"
				displayed = ", ".join(item[0] for item in find_values)
				related = ", ".join(item for lst in find_values for item in lst[1:])
				related_msg = f"\n-# Not what you are looking for? View related items: {related}" if related and settings.view_related_items else ""

				
				msg = f"{prefix} {noun}: {displayed}{related_msg}"
				await plenary.edit(content=msg.strip())
			
			except Exception as e:
				traceback.print_exception(type(e), e, e.__traceback__)
				embed = discord.Embed(
					colour=discord.Colour.red(),
					title=f":x: An error occurred",
					description=f"```{e}```"
				)

				await message.reply(embed=embed)

async def setup(bot: SDWikiBot):
	await bot.add_cog(EventsCog(bot))