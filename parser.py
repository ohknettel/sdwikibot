from lxml import html
from copy import deepcopy
from enum import IntEnum
from dataclasses import dataclass
import urllib.parse
import mwparserfromhell
import re
import customs

TAB_SUBST = "‎ ‎ ‎‎ ‎  ‎ ‎ "
REF_RE = re.compile(r"\||#")
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
	code = mwparserfromhell.parse(text)
	referencable = []
	nodes_to_remove = []
	nodes_to_replace = []
	
	for node in code.nodes:
		node_type = type(node)
		
		if node_type == mwparserfromhell.nodes.Tag:
			text_content = node.strip()
			
			if "span" in text_content:
				fragments = html.fragments_fromstring(text_content)
				if fragments:
					el = next((f for f in fragments if isinstance(f, html.HtmlElement)), None)
					if el is not None and el.get("id"):
						referencable.append(ReferencableObject(
							ReferencableObjectType.SPAN,
							text_content,
							el.get("id")
						))
			
			elif "div" in text_content:
				fragments = [t for t in html.fragments_fromstring(text_content) if isinstance(t, html.HtmlElement)]
				for fragment in fragments:
					if fragment.tag == "div" and "mw-collapsible" in fragment.classes:
						nodes_to_remove.append(node)
						break
				else:
					nodes_to_replace.append((node, node.contents.strip_code()))
			
			elif "<ref" in text_content:
				nodes_to_remove.append(node)
		
		elif node_type == mwparserfromhell.nodes.Wikilink:
			if node.title.startswith("Category:"):
				nodes_to_remove.append(node)
		
		elif node_type == mwparserfromhell.nodes.Heading:
			node_cp = deepcopy(node)
			referencable.append(ReferencableObject(
				ReferencableObjectType.HEADER,
				str(node),
				node_cp.strip("=").strip(),
				node.count("=") // 2,
			))
	
	for node in nodes_to_remove:
		code.remove(node)
	
	for node, replacement in nodes_to_replace:
		code.replace(node, replacement)
	
	return WHITESPACE_RE.sub(r"\n\n", str(code)).strip(), referencable

def get_reference(reference: str, text: str):
	text_content, referencable = extract_referencable(text)

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
		
		if node_type == mwparserfromhell.nodes.Wikilink:
			title = node.title.strip()
			display = node.text
			replacements.append((node, url_format % (display or title, api_to_page_url(host["api_url"], title))))
		
		elif node_type == mwparserfromhell.nodes.ExternalLink:
			url = node.url.strip()
			title = node.title
			replacement = url_format % (title.strip(), url) if title else url
			replacements.append((node, replacement))
		
		elif node_type == mwparserfromhell.nodes.Tag:
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
		
		elif node_type == mwparserfromhell.nodes.Heading:
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
