from bot import SDWB2
from discord.ext.commands import Cog
from collections import defaultdict

import urllib.parse
import re 
import customs
import aiohttp
import asyncio

import discord
import tinydb
import orjson
import difflib
import cachetools
import sentence_splitter

BRACKETS_PATTERN = re.compile(r"\[\[(.+?)\]\]")
REFERENCES_PATTERN = re.compile(r"[:'| ]*(?:<(?P<html>\w+)\s*[^>]*?id=[\"\']([^\"\']+)[\"\'][^>]*>\s?(.+?)\s*</(?P=html)>|^=+\s?(.+?)\s?=+$)", re.MULTILINE | re.DOTALL)
HYPERLINKS_PATTERN = re.compile(r"\[\[(#?[^\[\]|]+?)(?:\|([^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*))?\]\]|\[(https?://[^\s\[\]]+)\s+([\w\s\S]+?)\]", re.MULTILINE)
HEADERS = {
	"User-Agent": f"sdwikibot/2.0 (@knettel; knettel.miraheze.org) discord.py/{discord.__version__}"
}

class EventsCog(Cog):
	def __init__(self, bot: SDWB2):
		self.bot = bot

	async def cog_load(self):
		self.cache = cachetools.TTLCache(maxsize=64, ttl=86400)
		self.search_cache = cachetools.Cache(maxsize=1024)
	   	
		connector = aiohttp.TCPConnector(limit=100, limit_per_host=10)
		self.session = aiohttp.ClientSession(connector=connector, headers=HEADERS)
		
		self.semaphore = asyncio.Semaphore(10)

	async def cog_unload(self):
		if hasattr(self, "session"):
			await self.session.close()

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
				pass

			return
		
		if len(matches_before) == 0 and len(matches_after) > 0:
			for chunk in chunks:
				if not chunk:
					continue

				self.cache[f"results:{after.id}"] = [await after.reply(chunk)]
		elif len(matches_before) <= len(matches_after):
			messages: list[discord.Message] | None = self.cache.get(f"results:{before.id}")
			if not messages:
				return

			i = 0
			for chunk in chunks:
				if not chunk:
					continue

				if i < len(messages):
					messages[i] = await messages[i].edit(content=chunk)
					i += 1
				else:
					messages.append(await after.reply(chunk))

			self.cache[f"results:{after.id}"] = [messages]
			
	async def smart_reference(self, _input: str, hosts: tinydb.TinyDB, url_format: str, preferences):
		matches = list(BRACKETS_PATTERN.finditer(_input))
		if not matches:
			return

		content_groups = defaultdict(lambda: {'sites': set(), 'tags': set()})
		for match in matches:
			content, allowed_sites, tags = self._parse_bracket_content(match.group(1))
			content_groups[content]["sites"].update(allowed_sites)
			content_groups[content]["tags"].update(tags)

		finds = defaultdict(set)
		pages: dict[str, list[customs.RevisionsPage]] = defaultdict(list)
		refs = defaultdict(list)
		query = tinydb.Query()

		for content, group_data in content_groups.items():
			allowed_sites, tags = group_data["sites"], group_data["tags"]

			if len(allowed_sites) > 0:
				allowed_hosts = list(
					filter(
						lambda host: host["name"] in allowed_sites and host.get("enabled", False), 
						hosts
					)
				)
			else:
				allowed_hosts = list(
					filter(
						lambda host: host.get("enabled", False), 
						hosts
					)
				)

			if not allowed_hosts:
				return

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
				titles = difflib.get_close_matches(content, [page["title"] for page in items], n=4, cutoff=0.1)
				
				for title in titles:
					page = next(item for item in items if item["title"] == title)
					page["host"] = host

					finds[title].add(host["name"])
					pages[title].append(page)
					refs[title] = sorted(tags)

		chunks = [""]
		maximum_character_limit = preferences.get(query.key == "maximum_reference_character_limit")
		if not maximum_character_limit or isinstance(maximum_character_limit, list):
			return
		elif not (max_character_limit := maximum_character_limit.get("value")):
			return

		if any(len(v) > 0 for v in refs.values()):
			chunk_list = await self.parse_wikitext({k: v for k, v in pages.items() if len(refs[k]) > 0}, refs, url_format, max_character_limit, finds)
			if chunk_list is False:
				return

			chunks = chunk_list

			if len(chunks) > 0:
				chunks[-1] += "\n\n"
			else:
				chunks = [""]
		
		self._format_links(preferences, pages, finds, chunks)

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

	def _split_dashes(self, string: str):
		parts = string.split("-")
		if len(parts) >= 2:
			return ["-".join(parts[:-1]), parts[-1]]
		return [string]

	async def parse_wikitext(self, pages: dict[str, list[customs.RevisionsPage]], refs: dict[str, list[str]], url_format: str, maximum_character_limit: int, finds: dict[str, set[str]]):
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
					matches = list(m for m in REFERENCES_PATTERN.finditer(page_content)
								   if m)

					end = -1
					if "->" in ref:
						ref, ref2 = list(filter(None, ref.split("->")))
						match2 = discord.utils.find(lambda m: m.groups() and ref2.lower() in [str(n).lower() for n in m.groups()], matches)
						if match2:
							index = matches.index(match2)
							if match2.group(4):
								end = match2.start()
							elif index + 1 < len(matches) and not matches[index + 1].group(3):
								end = matches[index + 1].start()
							else:
								end = match2.end()

					match = discord.utils.find(lambda m: m.groups() and ref.lower() in [str(n).lower() for n in m.groups()], matches)
					if not match:
						continue

					index = matches.index(match)
					group = 3 if match.group(3) else 4

					start = match.start()
					if end < 0:
						try:
							if group == 3:
								end = next(m for m in matches[index + 1:] if m.group(group) or m.group(4)).start()
							else:
								for m in matches[index + 1:]:
									mg = m.group(0)
									if mg.count("=") == match.group(0).count("="):
										end = m.start()
										break

								if end < 0:
									raise StopIteration()
						except StopIteration:
							end = len(page_content)

					catched = page_content[start:end].strip()
					if len(catched) > maximum_character_limit:
						return False
					elif catched == match.group(0).strip():
						continue

					string = self._parse_hyperlinks(
						self._parse_formatting(catched),
						page, url_format
					)
					

					if len(string) > chunk_limit:
						paragraphs = string.strip().replace("\n", "\n\n").split("\n\n")

						for idx, paragraph in enumerate(paragraphs):
							paragraph = paragraph.strip()
							if paragraph:
								paragraph = re.sub(r"^:+", lambda m: " ​  ​ " * len(m.group(0)), paragraph)
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
						if "\n" in string:
							for line in string.splitlines():
								if not line:
									continue

								line = re.sub(r"^:+", lambda m: " ​  ​ " * len(m.group(0)), line)
								builder.append("> " + line)

							builder.append(f"- *{url_format % (page["title"], page["fullurl"])}* ({rcp}){f" [{page["host"]["name"]}]" if include_hosts else ""}\n\n")
						else:
							string = re.sub(r"^:+", lambda m: " ​  ​ " * len(m.group(0)), string)
							builder.append(f"> {string}")
							builder.append(f"- *{url_format % (page["title"], page["fullurl"])}* ({rcp}){f" [{page["host"]["name"]}]" if include_hosts else ""}\n\n")
						
						if len(chunks[-1] + "\n".join(builder)) < chunk_limit:
							chunks[-1] += "\n".join(builder)
						else:
							chunks.append("\n".join(builder))

					found_ref = True

				if found_ref:
					pages[title].remove(page)
					if title in finds:
						finds[title].remove(page["host"]["name"])

		return chunks

	def _parse_hyperlinks(self, content: str, page: customs.RevisionsPage, url_format: str):
		for match in HYPERLINKS_PATTERN.finditer(content):
			iw_link, iw_text, ex_link, ex_text = match.groups()

			if iw_link:
				if iw_link.startswith("#"):
					repl = url_format % (iw_text, page["fullurl"] + iw_link)
				elif iw_text:
					repl = url_format % (iw_text, self._api_to_page_url(page["host"]["api_url"], iw_link))
				else:
					repl = url_format % (iw_link, self._api_to_page_url(page["host"]["api_url"], iw_link))
				
				content = content.replace(match.group(0), repl)
			
			if ex_link and ex_text:
				repl = url_format % (ex_text, ex_link)
				content = content.replace(match.group(0), repl)

		return content

	def _parse_formatting(self, content: str):
		content = re.sub(r"^(?P<hdr>=+)\s?(.+?)\s?(?P=hdr)", lambda m: "#" * len(m.group(1)) + f" {m.group(2)}", content, flags=re.MULTILINE)
		content = content.replace("*", "•").replace("'''", "**").replace("''", "*")
		content = re.sub(r"<ref\b[^>]*?(?:\/>|>.*?<\/ref>)", "", content)
		content = re.sub(r"<[^>]*>|\|?}|^\|\s?", "", content)
		return content

	def _api_to_page_url(self, api_url: str, page_title: str) -> str:
		parsed = urllib.parse.urlparse(api_url)
		base_url = f"{parsed.scheme}://{parsed.netloc}"
		safe_title = urllib.parse.quote(page_title.replace(' ', '_'), safe='')
		
		if '/w/api.php' in parsed.path:
			return f"{base_url}/wiki/{safe_title}"
		else:
			base_path = parsed.path.replace('/api.php', '')
			return f"{base_url}{base_path}/index.php?title={safe_title}"

	def _parse_bracket_content(self, content: str):
		title, allowed_sites, tags = content, [], []
		if "|" in content:
			title, allowed_sites = content.split("|", 1)
			allowed_sites = [site.strip() for site in allowed_sites.split(",")]
		if "#" in title:
			title, tag_str = title.split("#", 1)
			tags = [tag.strip() for tag in tag_str.split("#")]
		return title.strip(), allowed_sites, tags

	def _format_links(self, preferences, pages: dict[str, list[customs.RevisionsPage]], finds: dict[str, set[str]], replies: list[str]):
		hyperlinks = []
		duplicates = {key for key, hosts in finds.items() if len(hosts) > 1}

		query = tinydb.Query()
		url_format = ("<%s>" if preferences.contains((query.key == "silence_result_urls") & (query.value == True)) 
					  else "%s")

		for title, matches in pages.items():
			if not matches:
				continue

			if title in duplicates:
				links = []
				for site in finds[title]:
					page = next((p for p in matches if p["host"]["name"] == site), matches[0])
					if page:
						links.append(f"[{site}]({url_format % page['fullurl']})")
						
				hyperlinks.append(f"*{title}* ({', '.join(links)})")
			else:
				hyperlinks.append(f"*[{title}]({url_format % matches[0]['fullurl']})*")

		if not hyperlinks:
			return

		if len(hyperlinks) == 1:
			message = f"Roger that! Here is your link: {hyperlinks[0]}"
		elif len(hyperlinks) > 1:
			message = f"Roger that! Here are your links: {hyperlinks[0]}\n"
			message += "-# Not what you are looking for? View related items: " + ", ".join(hyperlinks[1:])
		else:
			return

		if len(replies[-1] + message) >= 2000 and len(replies[-1]) > 0:
			replies.append("")
		replies[-1] = f"{replies[-1].rstrip()}\n\n{message.lstrip()}"

async def setup(bot: SDWB2):
	await bot.add_cog(EventsCog(bot))
