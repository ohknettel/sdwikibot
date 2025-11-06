from lxml import html
from copy import deepcopy
from enum import IntEnum
from dataclasses import dataclass
import urllib.parse
import mwparserfromhell
import re
import customs
import textwrap

TAB_SUBST = "‎ ‎ ‎‎ ‎  ‎ ‎ "
REF_RE = re.compile(r"\||#")
DIV_RE = re.compile(r"<div[^<>]*>.+?</div>", re.DOTALL)
WHITESPACE_RE = re.compile(r"\s{3,}")

class ReferencableObjectType(IntEnum):
	HEADER = 0
	SPAN = 1

@dataclass
class ReferencableObject:
	object_type: ReferencableObjectType
	text: str
	reference: str
	level: int = -1

def extract_referencable(text: str):
	text = re.sub(DIV_RE, "", text)
	text = re.sub(WHITESPACE_RE, "\n", text)

	code = mwparserfromhell.parse(text)
	referencable = []

	for heading in code.filter_headings():
		heading_cp = deepcopy(heading)
		referencable.append(ReferencableObject(
			ReferencableObjectType.HEADER,
			str(heading),
			heading_cp.strip("=").strip(),
			heading.count("=") // 2,
		))

	for tag in code.filter_tags():
		if tag.tag == "span":
			try:
				element: html.HtmlElement = html.fragment_fromstring(str(tag))
				if (_id := element.get("id")):
					referencable.append(ReferencableObject(
						ReferencableObjectType.SPAN,
						str(tag.contents),
						_id
					))
			finally:
				code.replace(tag, tag.contents)
		elif tag.tag == "ref":
			code.remove(tag)
	
	return WHITESPACE_RE.sub(r"\n\n", str(code)).strip(), referencable

def get_reference(reference: str, text: str):
	text_content, referencable = extract_referencable(textwrap.dedent(text).strip())

	if not referencable:
		return None

	contents = []
	references = [ref for ref in REF_RE.split(reference) if ref]
	
	for ref in references:
		next_ref = None
		if "->" in ref:
			ref, ref2 = ref.split("->", 1)
			next_ref = next((r for r in referencable if r.reference.lower() == ref2.strip().lower()), None)
		
		match = next((r for r in referencable if r.reference.lower() == ref.strip().lower()), None)
		if not match:
			continue
		
		start = text_content.index(match.text)
		while start > 0 and text_content[start - 1] in ":* ":
			start -= 1
		
		if not next_ref:
			match_idx = referencable.index(match)
			next_ref = next((ref for ref in referencable[match_idx + 1:] if ref.object_type == match.object_type), None)
		
		if next_ref:
			content = text_content[start:text_content.index(next_ref.text)].strip()
		else:
			content = text_content[start:].strip()
		
		if content:
			contents.append(content)
	
	return contents

def api_to_page_url(api_url: str, page_title: str) -> str:
	parsed = urllib.parse.urlparse(api_url)
	base_url = f"{parsed.scheme}://{parsed.netloc}"
	safe_title = urllib.parse.quote(page_title.replace(' ', '_'), safe='')
	
	if '/w/api.php' in parsed.path:
		return f"{base_url}/wiki/{safe_title}"
	else:
		base_path = parsed.path.replace('/api.php', '')
		return f"{base_url}{base_path}/index.php?title={safe_title}"

def format_wikitext(text: str, host: customs.Host, url_format: str = "[%s](%s)"):
	code = mwparserfromhell.parse(text)
	replacements = []
	removals = []
	
	for node in code.nodes:
		node_type = type(node)
		
		if isinstance(node, mwparserfromhell.nodes.Wikilink):
			title = node.title.strip()
			display = node.text
			replacements.append((node, url_format % (display or title, api_to_page_url(host["api_url"], title))))
		
		elif isinstance(node, mwparserfromhell.nodes.ExternalLink):
			url = node.url.strip()
			title = node.title
			replacement = url_format % (title.strip(), url) if title else url
			replacements.append((node, replacement))
		
		elif isinstance(node, mwparserfromhell.nodes.Tag):
			if node.tag == "dd":
				replacements.append((node, TAB_SUBST))
			elif node.tag == "i":
				replacements.append((node, f"*{node.contents.strip_code()}*"))
			elif node.tag == "b":
				replacements.append((node, f"**{node.contents.strip_code()}**"))
			elif node.tag == "u":
				replacements.append((node, f"__{node.contents.strip_code()}__"))
			elif node.tag == "span":
				replacements.append((node, node.contents.strip_code()))
		
		elif isinstance(node, mwparserfromhell.nodes.Heading):
			if node.level <= 3:
				replacements.append((node, f"{'#' * node.level} {node.title.strip()}"))
			else:
				replacements.append((node, f"**{node.title.strip()}**"))
		
		elif node_type != mwparserfromhell.nodes.Text:
			removals.append(node)
	
	for node, replacement in replacements:
		code.replace(node, replacement)
	
	for node in removals:
		code.remove(node)
	
	return code.strip()

def get_title_tags(text: str):
	parts = REF_RE.split(text)
	return parts[0].strip(), [p.strip() for p in parts[1:]]

if __name__ == "__main__":
	import orjson
	import asyncio, aiohttp

	async def main():
		async with aiohttp.ClientSession() as session:
			params = {
				"action": "query",
				"format": "json",
				"generator": "search",
				"gsrwhat": "title",
				"gsrlimit": 25,
				"gsrsearch": "File:JudiciarySeal.webp",
				"prop": "info|revisions|imageinfo",
				"inprop": "url",
				"iiprop": "url",
				"iilimit": 1,
				"rvprop": "content",
				"rvslots": "main",
				"formatversion": 2
			}

			response = await session.get("https://qwrky.dev/mediawiki/api.php", params=params)
			if response.status != 200:
				print(f"Status code {response.status} for request File:JudiciarySeal.webp: {await response.text()}")
				return None

			data = orjson.loads(await response.text())
			if not data.get("query", {}).get("pages"):
				return None

			print(data)
			items = data["query"]["pages"][:7]
			if len(items) > 0:
				print(items)

	asyncio.run(main())