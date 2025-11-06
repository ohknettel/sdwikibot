from bot import SDWB2
from discord.ext.commands import Cog
from collections import defaultdict
from rapidfuzz import process, fuzz

import re 
import customs
import parser
import aiohttp
import asyncio

import discord
import tinydb
import orjson
import cachetools
import sentence_splitter
import traceback

BRACKETS_PATTERN = re.compile(r"\[\[(.+?)\]\]")

SAFE = lambda s: quote(s, ":/")

def prefix_sort(text, query):
	if len(query) < 3:
		return 0
		
	text_lower = text.lower()
	query_lower = query.lower()
	
	max_check = min(len(text_lower), len(query_lower))
	score = 0
	
	for i in range(max_check):
		if text_lower[i] == query_lower[i]:
			score += 1
		else:
			break
			
	return score if score >= 3 else 0

class EventsCog(Cog):
	def __init__(self, bot: SDWB2):
		self.bot = bot

	async def cog_load(self):
		self.cache = cachetools.TTLCache(maxsize=64, ttl=86400)
		self.search_cache = cachetools.TTLCache(maxsize=256, ttl=1800)		
		self.semaphore = asyncio.Semaphore(10)

	async def get_guild_preferences(self, guild: discord.Guild) -> tinydb.TinyDB:
		if f"pref:{guild.id}" not in self.cache:
			self.cache[f"pref:{guild.id}"] = await self.bot.get_guild_preferences(guild)

		return self.cache[f"pref:{guild.id}"]

	@Cog.listener()
	async def on_ready(self):
		print(f"Logged in as {self.bot.user}")

	@Cog.listener()
	async def on_message(self, message: discord.Message):
		if (message.author.bot or not message.guild
			or not BRACKETS_PATTERN.search(message.content.strip())):
			return

		preferences = await self.get_guild_preferences(message.guild)
		query = tinydb.Query()

		url_format = "[%s](%s)"
		if not preferences.contains((query.key == "smart_referencing") & (query.value == True)):
			return
		elif preferences.contains((query.key == "silence_result_links") & (query.value == True)):
			url_format = "[%s](<%s>)"

		stripped = message.content.strip()
		hosts = self.bot.hosts

		chunks = await self.smart_reference(stripped, hosts, url_format, preferences)
		if not chunks:
			try:
				await message.author.send(f"**Your reference exceeds the maximum character limit! Please revise your references and try again!**\n{message.jump_url}")
			except discord.Forbidden:
				pass
			return

		messages = []
		for chunk in chunks:
			if not chunk:
				continue

			messages.append(await message.reply(chunk.strip()[:2000]))

		self.cache[f"results:{message.id}"] = messages

	@Cog.listener()
	async def on_message_edit(self, before: discord.Message, after: discord.Message):
		if (before.author.bot or not before.guild
			or not BRACKETS_PATTERN.search(after.content.strip())):
			return

		preferences = await self.get_guild_preferences(before.guild)
		query = tinydb.Query()

		url_format = "[%s](%s)"
		if not preferences.contains((query.key == "smart_referencing") & (query.value == True)):
			return
		elif preferences.contains((query.key == "silence_result_links") & (query.value == True)):
			url_format = "[%s](<%s>)"

		if preferences.contains((query.key == "reference_on_edit") & (query.value == False)):
			return

		matches_before = BRACKETS_PATTERN.findall(before.content.strip())
		matches_after = BRACKETS_PATTERN.findall(after.content.strip())

		if matches_before == matches_after:
			return

		stripped = after.content.strip()
		hosts = self.bot.hosts

		chunks = await self.smart_reference(stripped, hosts, url_format, preferences)
		if not chunks:
			try:
				await after.author.send(f"**Your reference exceeds the maximum character limit! Please revise your references and try again!**\n{after.jump_url}")
			except discord.Forbidden:
				return
			finally:
				return
		
		if len(matches_before) == 0 and len(matches_after) > 0:
			for chunk in chunks:
				if not chunk:
					continue

				self.cache[f"results:{after.id}"] = [await after.reply(chunk)]
		elif len(matches_before) <= len(matches_after):
			messages: list[discord.Message] | None = self.cache.get(f"results:{before.id}", [])
			if not messages:
				for chunk in chunks:
					if not chunk:
						continue

					messages.append(await after.reply(chunk))
			else:
				i = 0
				for chunk in chunks:
					if not chunk:
						continue

					if i < len(messages):
						messages[i] = await messages[i].edit(content=chunk)
						i += 1
					else:
						messages.append(await after.reply(chunk))

			self.cache[f"results:{after.id}"] = messages
			
	async def smart_reference(self, _input: str, hosts: tinydb.TinyDB, url_format: str, preferences):
		matches = list(BRACKETS_PATTERN.finditer(_input))
		if not matches:
			return

		finds = defaultdict(set)
		pages: dict[str, list[customs.RevisionsPage]] = defaultdict(list)
		refs = defaultdict(list)
		cgroups: dict[str, list[customs.RevisionsPage]] = defaultdict(list)

		for match in matches:
			if not match or not (content := match.group(1)):
				continue

			content, tags = parser.get_title_tags(content)

			allowed_hosts = hosts.all()
			search_tasks = [self.search_host_cached(host, content) for host in allowed_hosts]
			search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

			for i, result in enumerate(search_results):
				if isinstance(result, BaseException):
					print(f"Host search error for {allowed_hosts[i]['name']}: {result}")
					continue
				if not result:
					continue

				host = allowed_hosts[i]
				items = result
				fuzzy = process.extract(content, [page["title"] for page in items], limit=4, scorer=fuzz.QRatio)
				
				for title, _, _ in fuzzy:
					page = next(item for item in items if item["title"] == title)
					page["host"] = host

					finds[title].add(host["name"])

					pages[title].append(page)
					cgroups[content].append(page)

					refs[title] = sorted(tags)

		chunks = [""]
		if any(len(v) > 0 for v in refs.values()):
			chunk_list = await self.parse_wikitext({k: v for k, v in pages.items() if len(refs[k]) > 0}, refs, url_format, cgroups)
			if chunk_list is False:
				return

			chunks = chunk_list

			if len(chunks) > 0:
				chunks[-1] += "\n\n"
			else:
				chunks = [""]
		
		self._format_links(preferences, cgroups, finds, chunks)

		return chunks
			
	async def search_host_cached(self, host, content: str):
		cache_key = "%s:%s" % (content, host["name"])
		if cache_key in self.search_cache:
			return self.search_cache[cache_key]

		async with self.semaphore:
			try:
				params = {
					"action": "query",
					"format": "json",
					"generator": "search",
					"gsrwhat": "title",
					"gsrlimit": 25,
					"gsrsearch": content,
					"prop": "info|revisions",
					"inprop": "url",
					"rvprop": "content",
					"rvslots": "main",
					"formatversion": 2
				}

				response = await self.session.get(host["api_url"], params=params)
				if response.status != 200:
					print(f"Status code {response.status} for request {content}: {await response.text()}")
					return None

				data = orjson.loads(await response.text())
				if not data.get("query", {}).get("pages"):
					return None

				items = data["query"]["pages"][:7]
				self.search_cache[cache_key] = items
				return items
			except Exception as e:
				print(f"Search error for {host["name"]}: {e}")
				return None

	async def parse_wikitext(self, pages: dict[str, list[customs.RevisionsPage]], refs: dict[str, list[str]], url_format: str, cgroups: dict):
		try:
			chunks: list[str] = []
			chunk_limit = 1700

			for title, items in pages.items():
				current = []
				include_hosts = len(items) > 1
				for page in items:
					found_ref = False
					for ref in refs[title]:
						rcp = ref
						if not page["revisions"]:
							continue

						page_content = page["revisions"][0]["slots"]["main"]["content"]
						contents = parser.get_reference(ref,  page_content)
						if not contents:
							continue

						for content in contents:
							string = parser.format_wikitext(content, page["host"], url_format)
							if len(string) > chunk_limit:
								paragraphs = string.strip().replace("\n", "\n\n").split("\n\n")

								for idx, paragraph in enumerate(paragraphs):
									paragraph = paragraph.strip()
									if paragraph:
										for i, sentence in enumerate(sentence_splitter.split_text_into_sentences(paragraph, "en")):
											current_sum = sum(len(text) for text in current)
											if current_sum + len(sentence) < chunk_limit:
												if i == 0:
													current.append("> " + sentence)
												else:
													current[-1] = f"{current[-1].rstrip()} {sentence}" 
											else:
												current.append(f"- *{url_format % (page["title"], page["fullurl"])}* ({rcp}){f" [{page["host"]["name"]}]" if include_hosts else ""}\n\n")
												chunks.append("\n".join(current))
												current.clear()
												current.append("> " + sentence)

									idx += 1

								if len(current) > 0:
									current.append(f"- *{url_format % (page["title"], page["fullurl"])}* ({rcp}){f" [{page["host"]["name"]}]" if include_hosts else ""}\n\n")
									chunks.append("\n".join(current))
									current.clear()
							else:
								if len(chunks) == 0:
									chunks.append("")
								
								builder = []

								string = string.rstrip("‎  \t")
								if "\n" in string:
									for line in string.splitlines():
										if not line:
											continue

										builder.append("> " + line)

									builder.append(f"- *{url_format % (page["title"], page["fullurl"])}* ({rcp}){f" [{page["host"]["name"]}]" if include_hosts else ""}\n\n")
								else:
									builder.append(f"> {string.strip()}")
									builder.append(f"- *{url_format % (page["title"], page["fullurl"])}* ({rcp}){f" [{page["host"]["name"]}]" if include_hosts else ""}\n\n")
								
								if len(chunks[-1] + "\n".join(builder)) < chunk_limit:
									chunks[-1] += "\n".join(builder)
								else:
									chunks.append("\n".join(builder))

						found_ref = True

					if found_ref:
						k = next(iter(n for n, v in cgroups.items() if any(p for p in v if p == page)))
						cgroups[k].remove(page)

			return chunks
		except Exception:
			traceback.print_exc()
			return []

	def _format_links(self, preferences, content_groups: dict[str, list[customs.RevisionsPage]], finds: dict, replies: list[str]):
		try:
			if not content_groups or not any(content_groups.values()):
				return

			m_hyperlinks = [] # main
			r_hyperlinks = [] # related

			duplicates = {key for key, hosts in finds.items() if len(hosts) > 1}
			query = tinydb.Query()
			url_format = ("<%s>" if preferences.contains((query.key == "silence_result_urls") & (query.value == True)) 
						  else "%s")

			for search, matches in content_groups.items():
				if not matches:
					continue

				best_match = max(matches, key=lambda p: prefix_sort(p["title"], search))
				other_matches = [match for match in matches if match["title"] != best_match["title"]]
			
				self._categorize_link(best_match, duplicates, m_hyperlinks, url_format, matches)

				for page in other_matches:
					self._categorize_link(page, duplicates, r_hyperlinks, url_format, matches)

			if not m_hyperlinks:
				return

			if len(m_hyperlinks) == 1:
				message = f"Roger that! Here is your link: {m_hyperlinks[0]}"
			elif len(m_hyperlinks) > 1:
				message = f"Roger that! Here are your links: {", ".join(m_hyperlinks)}\n"
			else:
				return
			
			if len(r_hyperlinks) > 0:
				message = message.rstrip() + "\n-# Not what you are looking for? View related items: " + ", ".join(r_hyperlinks)

			if len(replies[-1] + message) >= 2000 and len(replies[-1]) > 0:
				replies.append("")
			replies[-1] = f"{replies[-1].rstrip()}\n\n{message.lstrip()}"
		except:
			traceback.print_exc()

	def _categorize_link(self, page, duplicates, storage, url_format, matches):
		title = page["title"]
		
		if title in duplicates:
			links = [
				f"[{match['host']['name']}]({url_format % match['fullurl']})"
				for match in matches 
				if match["host"]["name"] != page["host"]["name"] and match["title"] == title
			]
			if links:
				storage.append(f"*{title}* ({', '.join(links)})")
		else:
			storage.append(f"*[{title}]({url_format % page['fullurl']})*")

async def setup(bot: SDWB2):
	await bot.add_cog(EventsCog(bot))
