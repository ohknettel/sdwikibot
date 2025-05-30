import asyncio, os, time, discord, mwclient, json;
from dataclasses import dataclass;
from discord.ext.commands import Bot, ExtensionError;
from pathlib import Path;
from cache import PickleCacheManager;

@dataclass
class Sites:
    wiki: mwclient.Site
    archives: mwclient.Site

class SDWikiBot(Bot):
    watcher: asyncio.Task

    def __init__(self, *args, sites: Sites, tm, **kwargs):
        super().__init__(*args, **kwargs)
        self.sites = sites
        self.tm = tm

    async def setup_hook(self):
        for cog in Path("cogs").glob("*.py"):
            if not cog.stem.startswith("_"):
                try:
                    await self.load_extension(".".join(cog.with_suffix("").parts))
                    print(f"[CLIENT] Loaded cog {cog.name}")
                except Exception as e:
                    print(f"[CLIENT] Failed to load cog {cog.name}: {e}")

        testing_guild_id = os.getenv("TESTING_GUILD_ID", None);
        if testing_guild_id:
            guild = discord.Object(id=testing_guild_id)
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            except Exception as e:
                raise e
        else:
            await self.tree.sync();

        await self.ensure_settings();
        self.watcher = asyncio.create_task(self.cog_watcher())

    def _return_settings(self, d={}):
        settings: dict = json.load(open("settings.json", "rb"))
        for _list in settings.values():
            for item in _list:
                if item["name"] not in d:
                    d[item["name"]] = item.get("default", None);
        return (settings, d);

    async def ensure_settings(self):
        if not os.path.exists("./settings/"):
            os.mkdir("./settings/");

        async for guild in self.fetch_guilds():
            db = PickleCacheManager.get_cache(f"settings/{guild.id}.pkl");
            settings, db = self._return_settings(db);
            db["metadata"] = settings;
            PickleCacheManager.sync_cache(f"settings/{guild.id}.pkl");

    def get_guild_settings(self, _id: int):
        return PickleCacheManager.get_cache(f"settings/{_id}.pkl");

    def sync_guild_settings(self, _id: int):
        PickleCacheManager.sync_cache(f"settings/{_id}.pkl");

    async def cog_watcher(self):
        print("[WATCHER] Watching for changes...")
        last = time.time()
        while True:
            reloads = {
                name for name, module in self.extensions.items()
                if module.__file__ and os.stat(module.__file__).st_mtime > last
            }
            for ext in reloads:
                try:
                    await self.reload_extension(ext)
                    print(f"[WATCHER] Hot reloaded {ext}")
                except ExtensionError as e:
                    print(f"[WATCHER] Could not hot reload {ext}: {e}")
            last = time.time()
            await asyncio.sleep(1)

    async def on_ready(self):
        self.start_time = time.time()
        print(f"[CLIENT] Logged in as {self.user}")