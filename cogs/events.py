from discord.ext.commands import Cog
from bot import SDWikiBot
from constants import neutral_colour
from difflib import SequenceMatcher
import discord, re, types, traceback, textwrap;

class EventsCog(Cog):
	def __init__(self, bot: SDWikiBot):
		self.bot = bot;

	@Cog.listener()
	async def on_message(self, message: discord.Message):
		if message.author.bot or not message.guild or not self.bot.user:
			return;
		settings = types.SimpleNamespace(**self.bot.get_guild_settings(message.guild.id));		

		content = message.content;
		if content == self.bot.user.mention and settings.help_on_mention:
			embed = discord.Embed(
				colour=neutral_colour,
				title=f"Welcome",
				description=textwrap.dedent(f"""
					The **S**im**D**emocracy**Wikibot** is a bot designed to fetch and display pages from both the wiki and archives.

					Browse and search pages, view statistics, display leaderboards and automatically reference pages through smart referencing by using `[[page]]` in your messages.
					
					Wish to start searching? Use `/search` and begin your journey of inquiries.
					Wish to configure the bot? Use `/settings list` to learn about the bot's settings and set them using `/settings set`.

					Want to report a bug or complain about technical difficulties? Please contact {(await self.bot.application_info()).owner.mention}.
				""")
			).set_thumbnail(url=self.bot.user.avatar);

			await message.reply(embed=embed);
		elif settings.toggle_smart_referencing:
			try:
				queries = re.findall(r"\[\[(.+?)\]\]", content);

				if len(queries) > 0:
					finds = {}
					for query in queries:
						props = {
							"generator": "search",
							"gsrsearch": query,
							"gsrwhat": "title",
							"gsrlimit": 25,
							"prop": "info",
							"inprop": "url",
						};

						results = []
						wiki_results = self.bot.sites.wiki.get("query", **props);
						archives_results = self.bot.sites.archives.get("query", **props);
						if (wiki_pages := wiki_results["query"].get("pages")) is not None:
							results += list(wiki_pages.values());

						if (archives_pages := archives_results["query"].get("pages")) is not None:
							results += list(archives_pages.values());

						url_format = "<%s>" if settings.silence_link_embeds else "%s";
						results.sort(key=lambda r: SequenceMatcher(None, r["title"].lower(), query.lower()).ratio(), reverse=True);
						formatted = [];
						for result in results:
							title = result["title"];
							url = url_format % result["fullurl"];
							hyperlink = f"[`{title}`]({url})";

							dup_titles = [index for index, r in enumerate(results) if r["title"] == title]
							if len(dup_titles) > 1:
								other_res = results.pop(max(dup_titles));
								other_url = url_format % other_res["fullurl"];
								site_name = "wiki" if "simdemocracy.miraheze.org" in url else "archives";
								other_site_name = "wiki" if site_name == "archives" else "archives";
								hyperlink = f"`{title} (`[`{site_name}`]({url})`, `[`{other_site_name}`]({other_url})`)`";

							formatted.append(hyperlink);

						finds[query] = formatted[:7];

					if len(finds) > 0 and all(len(e) > 0 for e in finds):
						find_values = list(finds.values());
						noun = "Links" if len(queries) > 1 else "Link";
						displayed = ", ".join(item[0] for item in find_values);
						related = ", ".join([item for lst in find_values for item in lst[1:]]);
						related_msg = f"\n-# Not what you are looking for? View related items: {related}" if related != "" else related;

						msg = f"{settings.link_prefix_message if settings.link_prefix_message and settings.link_prefix_message != 'None' else ''} {noun}: {displayed}" \
								+ (related_msg if settings.view_related_items else "");
						await message.reply(msg.strip());
			except Exception as e:
				traceback.print_exception(type(e), e, e.__traceback__);
				embed = discord.Embed(
					colour=discord.Colour.red(),
					title=f":x: An error occurred",
					description=f"```{e}```"
				)

				await message.reply(embed=embed);

async def setup(bot: SDWikiBot):
	await bot.add_cog(EventsCog(bot))