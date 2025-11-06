from typing import TypedDict, NamedTuple
from dataclasses import dataclass, field
from datetime import datetime
from dateutil.parser import parse

from fastembed import TextEmbedding
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

import aiosqlite
import asyncio
import aiohttp
import mwparserfromhell
import re
import numpy as np
import pickle
import faiss
import traceback

R1 = re.compile(r"'''(.+?)'''|''(.+?)''", re.MULTILINE)
R2 = re.compile(r"(?:Acting ?)?(?:Chief ?)?(?:Justice|Judge|Magistrate) ?[^\s]+", re.MULTILINE)
R3 = re.compile(r"<[^>]*>", re.MULTILINE)
TABLE = re.compile(r"\{\|.*?\|\}", re.DOTALL)
PAT = re.compile(r"[^span<>id\"'\/]+")

@dataclass
class Result:
	date: datetime | None = field(init=False, default=None)
	title: str
	url: str
	jurisdiction: str | None
	judges: str = field(init=False, default="")
	touched: int = field(init=False, default=0)
	precedents: list[str] = field(init=False, default_factory=list)

class SearchData(NamedTuple):
	case_title: str
	case_url: str
	precedent: str

class SearchResult(TypedDict):
	data: SearchData
	distance: float

model = TextEmbedding(specific_model_path="models/snowflake/snowflake-arctic-embed-xs", cache_dir="./model_cache")

def embed(text: str):
	return next(n for n in model.query_embed(text))

def str_to_timestamp(val: str):
	return int(parse(val).timestamp())

def preprocess_text(text):
	stop_words = set(stopwords.words('english'))
	tokens = word_tokenize(text)
	tokens = [token.lower() for token in tokens if token.isalpha() and token.lower() not in stop_words]
	return " ".join(tokens)

def clean_wikitext(wikitext):
	wikitext = TABLE.sub("", wikitext)
	parsed_wiki = mwparserfromhell.parse(wikitext)

	for node in parsed_wiki.nodes:
		if isinstance(node, mwparserfromhell.nodes.Wikilink):
			if node.title.startswith('Category:'):
				parsed_wiki.remove(node)
			else:
				if node.text:
					node.replace(node, node.text)
				else:
					node.replace(node, node.title)
		
		elif isinstance(node, mwparserfromhell.nodes.ExternalLink):
			if node.title:
				node.replace(node, node.title)
			else:
				node.replace(node, '')
		
		elif isinstance(node, (mwparserfromhell.nodes.Heading, mwparserfromhell.nodes.Tag)):
			if isinstance(node, mwparserfromhell.nodes.Tag) and node.tag in ["i", "u", "b", "strong"]:
				parsed_wiki.replace(node, node.contents)
			else:
				parsed_wiki.remove(node)
	
	cleaned_text = str(parsed_wiki.strip_code())
	return cleaned_text.strip()

def extract_precedent_column(wikitext, robj: Result):
	table = TABLE.search(wikitext)
	if not table:
		return

	code = mwparserfromhell.parse(table.group(0))

	rows = code.filter_tags(matches=lambda node: node.tag == "tr")
	for row in rows:
		cells = [c.contents.strip() for c in row.contents.filter_tags(matches=lambda node: node.tag in ["td", "th"])]
		if len(cells) < 2:
			continue

		name, content = cells[0], cells[1]
		if "date" in name.lower():
			try:
				robj.date = parse(content)
			except:
				continue

		elif "judge" in name.lower() or "justice" in name.lower() or "judicial officer" in name.lower():
			content = content.replace("'''", "")
			content = content.replace("<br />", "").replace("<br/>", "")
			matches = list(filter(None, R2.findall(content)))
			if len(matches) > 0:
				robj.judges = ", ".join(matches)

		elif "precedent" in name.lower():
			if len(content.strip("*' \n")) <= 0:
				continue

			for item in content.splitlines():
				item = clean_wikitext(item)

				item = R1.sub(r"\1\2", item).strip(" -*\n")
				item = item.lstrip(" *-")
				item = R3.sub("", item).strip()

				if len(item) <= 10:
					continue

				item = item.replace("  ", " ")

				robj.precedents.append(item)

def chunkify(lst, size):
	for i in range(0, len(lst), size):
		yield lst[i:i + size]

async def get_predecent_chunked(chunk: list[dict]):
	results = []
	for item in chunk:
		title = item["title"]
		url = item["fullurl"]
		if not item.get("revisions"):
			continue
		
		wt = item["revisions"][0]["slots"]["main"]["content"]

		jurisdiction = None
		if "SDSC" in title:
			jurisdiction = "Supreme Court"
		elif "MIC" in title or "MCiv" in title:
			jurisdiction = "Minecraft Inferior Courts"
		elif "SDCA" in title:
			jurisdiction = "Court of Appeals"
		elif "SDCR" in title or "SDCoR" in title:
			jurisdiction = "Court of Review"
		elif any(word in title for word in ["Civ", "Crim", "SDIC"]):
			jurisdiction = "Inferior Courts"

		res = Result(title, url, jurisdiction)
		res.touched = int(datetime.strptime(item["touched"], "%Y-%m-%dT%H:%M:%SZ").timestamp())
		extract_precedent_column(wt, res)
		results.append(res)

	return results

async def fetch_cases(session: aiohttp.ClientSession):
	params = {
		"action": "query",
		"generator": "categorymembers",
		"gcmtitle": "Category:Case Law",
		"gcmtype": "page",
		"gcmlimit": "50",
		"prop": "revisions|info",
		"rvprop": "content",
		"rvslots": "main",
		"inprop": "url",
		"formatversion": "2",
		"format": "json"
	}

	members = []
	cmcontinue = None

	while True:
		if cmcontinue:
			params["gcmcontinue"] = cmcontinue

		res = await session.get("https://qwrky.dev/mediawiki/api.php", params=params)
		data = await res.json()
		members.extend(data["query"].get("pages", []))
		cmcontinue = data.get("continue", {}).get("gcmcontinue")
		if not cmcontinue:
			break

	return members

async def fetch():
	async with aiohttp.ClientSession() as session, aiosqlite.connect("index.db") as conn:
		conn.row_factory = aiosqlite.Row
		await conn.execute("PRAGMA journal_mode=WAL;")
		await conn.execute("PRAGMA synchronous=NORMAL;")
		await conn.execute("PRAGMA temp_store=MEMORY;")

		cur = await conn.cursor()

		await cur.executescript("""
			CREATE VIRTUAL TABLE IF NOT EXISTS precedents USING fts5(
				precedent,
				case_title,
				case_url,
				tokenize = "porter unicode61 remove_diacritics 2 tokenchars '-_'"
			);

			CREATE TABLE IF NOT EXISTS precedent_vectors (
				rowid INTEGER PRIMARY KEY,
				vector BLOB
			);

			CREATE TABLE IF NOT EXISTS case_info (
				case_title TEXT PRIMARY KEY,
				case_url TEXT,
				case_date INTEGER,
				case_judges TEXT,
				jurisdiction TEXT,
				touched INTEGER
			);
			
			CREATE INDEX IF NOT EXISTS idx_precedent_vectors_rowid ON precedent_vectors(rowid);
		""")

		await conn.commit()

		try:
			cases = await fetch_cases(session)
			chunks = list(chunkify(cases, 20))
			results = await asyncio.gather(*[get_predecent_chunked(chunk) for chunk in chunks])
			flattened: list[Result] = [result for lst in results for result in lst]
			texts = [preprocess_text(p) for res in flattened for p in res.precedents]
		except Exception:
			traceback.print_exc()
			return
		
		vectors = list(model.passage_embed(texts))
		rowids = []
		for result in flattened:
			if not result.date:
				continue

			for precedent in result.precedents:
				await cur.execute(
					"""INSERT INTO precedents(precedent, case_title, case_url) VALUES (?, ?, ?)""",
					(precedent, result.title, result.url)
				)
				
				precedent_id = cur.lastrowid
				if precedent_id is None:
					raise RuntimeError("Failed to insert precedent")
				
				rowids.append(precedent_id)
			
			await cur.execute(
				"""INSERT INTO case_info(case_title, case_url, case_date, case_judges, jurisdiction, touched) VALUES (?, ?, ?, ?, ?, ?)""", 
				(result.title, result.url, int(result.date.timestamp()), result.judges, result.jurisdiction, result.touched)
			)

		try:
			serialized_vectors = [pickle.dumps(vec) for vec in vectors]
			await conn.executemany(
				"INSERT INTO precedent_vectors(rowid, vector) VALUES (?, ?)",
				list(zip(rowids, serialized_vectors))
			)
			await conn.commit()

		except Exception as e:
			print(f"Vector insert failed: {e}")
			return
		
		print("Done!")

async def load_index(conn: aiosqlite.Connection) -> tuple[faiss.IndexFlatL2 | None, np.ndarray | None, list]:
	cursor = await conn.execute(f"""
		SELECT rowid, vector FROM precedent_vectors
	""")
	
	rows = await cursor.fetchall()
	if not rows:
		return None, None, []

	rowids = [row[0] for row in rows]
	v = [pickle.loads(row[1]) for row in rows]
	vectors = np.stack(v)

	index = faiss.IndexFlatL2(vectors.shape[-1])
	index.add(vectors) # type: ignore
	
	return index, vectors, rowids

def mmr_rerank(query_emb, candidate_embs, lambda_param: float, final_k: int = 40):
	query_sims = np.dot(candidate_embs, query_emb.T).flatten()
	doc_sims = np.dot(candidate_embs, candidate_embs.T)
	
	selected = []
	remaining = list(range(len(candidate_embs)))
	
	while len(selected) < final_k and remaining:
		scores = []
		for i in remaining:
			if not selected:
				score = query_sims[i]
			else:
				max_sim = np.max(doc_sims[i, selected])
				score = lambda_param * query_sims[i] - (1 - lambda_param) * max_sim
			scores.append(score)
		
		best_idx = np.argmax(scores)
		selected.append(remaining.pop(best_idx))
	
	return selected

D_MIN = 0.2
D_CUTOFF = 0.34
LAMBDA = 0.9

class PrecedentSearch:
	def __init__(self, connection: aiosqlite.Connection, session: aiohttp.ClientSession):
		self.conn = connection
		self.session = session
		self.index = faiss.IndexFlatL2()

	async def load_index(self):
		cursor = await self.conn.execute(f"""
			SELECT rowid, vector FROM precedent_vectors
		""")
		
		rows = await cursor.fetchall()
		if not rows:
			return None, None, []

		rowids = [row[0] for row in rows]
		v = [pickle.loads(row[1]) for row in rows]
		vectors = np.stack(v).astype(np.float32)

		print(vectors.shape)

		self.index = faiss.IndexFlatL2(vectors.shape[-1])
		self.index.add(vectors) # type: ignore
		self.vectors = vectors
		self.rowids = rowids

	async def reload_index(self):
		cases = await self._fetch_cases()
		to_change = []
		for case in cases:
			res = await (await self.conn.execute("SELECT touched FROM case_info WHERE case_title = ?", (case["title"],))).fetchone()
			if not res:
				to_change.append(case)
				continue

			stored_dt = datetime.fromtimestamp(res[0])
			touched = datetime.strptime(case["touched"], "%Y-%m-%dT%H:%M:%SZ")

			if touched > stored_dt:
				ids = await (await self.conn.execute("SELECT rowid FROM precedents WHERE case_title = ?", (case["title"],))).fetchall()
				for tupl in ids:
					_id = tupl[0]
					await self.conn.execute("DELETE FROM precedent_vectors WHERE rowid = ?", (_id,))
					await self.conn.execute("DELETE FROM precedents WHERE rowid = ?", (_id,))

				await self.conn.commit()
				to_change.append(case)

		if len(to_change) > 0:
			print("Updating for:", [t["title"] for t in to_change])
			await self.format_cases(to_change)
		else:
			print("Up to date index")

	async def format_cases(self, cases):
		cur = await self.conn.cursor()
		chunks = list(chunkify(cases, 20))
		results = await asyncio.gather(*[get_predecent_chunked(chunk) for chunk in chunks])
		flattened: list[Result] = [result for lst in results for result in lst]
		texts = [preprocess_text(p) for res in flattened for p in res.precedents]
		vectors = list(model.passage_embed(texts))

		rowids = []
		for result in flattened:
			if not result.date:
				continue

			print(result.title)

			for precedent in result.precedents:
				await cur.execute(
					"""INSERT INTO precedents(precedent, case_title, case_url) VALUES (?, ?, ?)""",
					(precedent, result.title, result.url)
				)
				
				precedent_id = cur.lastrowid
				assert(precedent_id)
				rowids.append(precedent_id)
			
			await cur.execute(
				"""INSERT INTO case_info(case_title, case_url, case_date, case_judges, jurisdiction, touched) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(case_title) DO UPDATE SET
							touched = excluded.touched""", 
				(result.title, result.url, int(result.date.timestamp()), result.judges, result.jurisdiction, result.touched)
			)

		await self.conn.executemany(
			"INSERT INTO precedent_vectors(rowid, vector) VALUES (?, ?)",
			[(rid, pickle.dumps(vec)) for rid, vec in zip(rowids, vectors)]
		)

		await self.conn.commit()
		await self.conn.execute("VACUUM")
		await self.load_index()

	async def _fetch_cases(self):
		params = {
			"action": "query",
			"generator": "categorymembers",
			"gcmtitle": "Category:Case Law",
			"gcmtype": "page",
			"gcmlimit": "50",
			"prop": "revisions|info",
			"rvprop": "content",
			"rvslots": "main",
			"inprop": "url",
			"formatversion": "2",
			"format": "json"
		}

		members = []
		cmcontinue = None

		while True:
			if cmcontinue:
				params["gcmcontinue"] = cmcontinue

			res = await self.session.get("https://qwrky.dev/mediawiki/api.php", params=params)
			data = await res.json()
			members.extend(data["query"].get("pages", []))
			cmcontinue = data.get("continue", {}).get("gcmcontinue")
			if not cmcontinue:
				break

		return members

	async def search(self, query: str, max_k: int = 40, *,
					jurisdiction: str | None = None,
					before: datetime | None = None,
					after: datetime | None = None,
					has_judge: str | None = None) -> list[SearchResult]:
		query_vector = next(embed for embed in model.query_embed(query))
		query_vector = query_vector.reshape(1, -1)
		faiss.normalize_L2(query_vector)

		distances, indices = self.index.search(query_vector, max_k) # type: ignore
		candidate_embs = self.vectors[indices[0]]
		selected = mmr_rerank(query_vector[0], candidate_embs, LAMBDA)
		
		selected_rowids = [self.rowids[indices[0][i]] for i in selected]
		
		sql = """
			SELECT p.rowid, p.case_title, p.case_url, p.precedent,
				   c.case_date, c.case_judges, c.jurisdiction
			FROM precedents p
			JOIN case_info c ON p.case_title = c.case_title
			WHERE p.rowid IN ({})
		""".format(','.join('?' * len(selected_rowids)))
		
		params = selected_rowids
		conditions = []
		
		if jurisdiction:
			conditions.append("c.jurisdiction = ?")
			params.append(jurisdiction)
		
		if before:
			conditions.append("c.case_date < ?")
			params.append(int(before.timestamp()))
		
		if after:
			conditions.append("c.case_date > ?")
			params.append(int(after.timestamp()))
		
		if has_judge:
			conditions.append("c.case_judges LIKE ?")
			params.append(f"%{has_judge}%")
		
		if conditions:
			sql += " AND " + " AND ".join(conditions)
		
		cursor = await self.conn.execute(sql, params)
		rows = await cursor.fetchall()
		
		row_dict = {row[0]: row for row in rows}
		
		results = []
		for i in selected:
			pos = indices[0][i]
			rowid = self.rowids[pos]
			distance = distances[0][i]
			
			if rowid not in row_dict:
				continue
			
			row = row_dict[rowid]
			_, case_title, case_url, precedent, _, _, _ = row
			
			if distance > D_MIN and distance < D_CUTOFF:
				results.append({
					"data": (case_title, case_url, precedent),
					"distance": float(distance)
				})
		
		return results

async def main():
	async with aiohttp.ClientSession() as session, aiosqlite.connect("index.db") as conn:
		try:
			searcher = PrecedentSearch(conn, session)
			await searcher.load_index()

			query = "executive authority"
			results = await searcher.search(query)
			print(results)
		except Exception:
			traceback.print_exc()
			return

if __name__ == "__main__":
	asyncio.run(main())