from discord.ext.commands import Bot, ExtensionError 
from pathlib import Path
from tinydb import Query, TinyDB

import os
import asyncio
import time
import orjson
import customs
import discord
import aiohttp
import aiosqlite

class SDWB2(Bot):
	def __init__(self, *args, session: aiohttp.ClientSession, **kwargs): # db: aiosqlite.Connection, session: aiohttp.ClientSession, **kwargs):
		super().__init__(*args, **kwargs)
		# self.db = db
		self.session = session

	async def setup_hook(self):
		cogs_path = Path("./cogs")
		for file in cogs_path.rglob("*.py"):
			if file.stem.startswith("__") or file.stem.endswith("__"):
				continue

			try:
				await self.load_extension(cogs_path.stem + "." + file.stem)
				print(f"Loaded cog {file.stem}")
			except Exception as e:
				print(f"Could not load cog {file.stem}: {e}")

		sync = os.getenv("SYNC", False)
		if sync:
			if isinstance(sync, str) and sync.lower().strip() != "true":
				pass

			guild = os.getenv("SYNC_GUILD", None)
			if guild:
				o = discord.Object(id=int(guild))
				self.tree.copy_global_to(guild=o)
				commands = await self.tree.sync(guild=o)
			else:
				commands = await self.tree.sync()

			print(f"Synced {len(commands)} commands")

		self.watcher = asyncio.create_task(self.cog_watcher())
		self.hosts = TinyDB("hosts.json")
		self.preference_defaults = orjson.loads(open("./preferences/defaults.json", "r").read())
		await self._ensure_preferences()

	async def cog_watcher(self):
		print("Watching for changes...")
		last = time.time()
		while True:
			reloads = {
				name for name, module in self.extensions.items()
				if module.__file__ and os.stat(module.__file__).st_mtime > last
			}
			for ext in reloads:
				try:
					await self.reload_extension(ext)
					print("Hot reloaded %s" % ext)
				except ExtensionError as e:
					print("Could not hot reload %s" % e)
			last = time.time()
			await asyncio.sleep(1)

	async def _ensure_preferences(self):
		async for guild in self.fetch_guilds():
			pref = TinyDB(f"./preferences/{guild.id}.json")
			for preference in self.preference_defaults:
				pq = Query()
				if not pref.contains(pq.key == preference["key"]):
					pref.upsert(preference, pq.key == preference["key"])

	async def get_guild_preferences(self, guild: discord.Guild):
		pref = TinyDB(f"./preferences/{guild.id}.json")
		if len(pref.all()) <= 0:
			await self._ensure_preferences()
		return pref

	def get_emojis(self, guild: discord.Guild):
		if not guild.me.guild_permissions.use_external_emojis:
			customs.Emojis.toggle_on = ":white_check_mark:"
			customs.Emojis.toggle_off = ":x:"
		return customs.Emojis