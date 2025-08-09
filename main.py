import asyncio
import sys
if sys.platform == "win32":
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from discord.ext.commands.bot import when_mentioned
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

import discord
import os
import winloop
from bot import SDWB2

async def main():
	async with SDWB2(command_prefix=when_mentioned, help_command=None, intents=discord.Intents.all(), logger=None, activity=discord.Activity(type=discord.ActivityType.watching, name="documents"), status=discord.Status.idle) as bot:
		try:
			await bot.start(os.getenv("TOKEN", ""))
		except (asyncio.CancelledError, KeyboardInterrupt):
			bot.loop.stop()
			sys.exit(0)

if __name__ == '__main__':
	winloop.install()
	winloop.run(main())