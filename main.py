import asyncio
import sys
if sys.platform == "win32":
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from discord.ext.commands.bot import when_mentioned
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

import discord
import os
#import uvloop
import winloop
import aiohttp
from bot import SDWB2

HEADERS = {
	"User-Agent": f"sdwikibot/2.0 (@knettel; knettel.miraheze.org) discord.py/{discord.__version__}"
}

async def main():
	connector = aiohttp.TCPConnector(limit=100, limit_per_host=10)
	async with aiohttp.ClientSession(connector=connector, headers=HEADERS) as session:
		async with SDWB2(
			command_prefix=when_mentioned,
			session=session,
			help_command=None,
			intents=discord.Intents.all(),
			activity=discord.Activity(type=discord.ActivityType.watching, name="documents"),
			status=discord.Status.idle) as bot:
			try:
				await bot.start(os.getenv("TOKEN", ""))
			except (asyncio.CancelledError, KeyboardInterrupt):
				bot.loop.stop()
				sys.exit(0)

if __name__ == '__main__':
	winloop.install()
	winloop.run(main())