import asyncio, os, time, discord, mwclient
from dataclasses import dataclass
from discord.ext.commands import Bot, ExtensionError
from pathlib import Path

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
                print(guild)
            except Exception as e:
                raise e
        # await self.tree.sync();

        self.watcher = asyncio.create_task(self.cog_watcher())

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

    async def on_app_command_error(self):
        pass;