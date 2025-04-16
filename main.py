import discord, asyncio, os, mwclient, tracemalloc;
from dotenv import load_dotenv;
from bot import SDWikiBot;

load_dotenv();
token = os.getenv("TOKEN");
api_url = os.getenv("MEDIAWIKI_API_URL", "simdemocracy.miraheze.org");
user_agent = os.getenv("MEDIAWIKI_USER_AGENT", "SDWikiBot (knettel)");

if not token:
	raise EnvironmentError("Bot token not supplied");

async def main():
	intents = discord.Intents.default();
	intents.message_content = True;
	intents.presences = True;

	tracemalloc.start();
	async with SDWikiBot(
		"",
		site=mwclient.Site(api_url, clients_useragent=user_agent),
		tm=tracemalloc,
		intents=intents,
		activity=discord.Activity(type=discord.ActivityType.watching, name="the wiki")
	) as bot:
		await bot.start(token);

if __name__ == "__main__":
	asyncio.run(main());