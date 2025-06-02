import discord, asyncio, os, mwclient, tracemalloc;
from dotenv import load_dotenv;
from bot import SDWikiBot, Sites;

load_dotenv();
token = os.getenv("TOKEN");
user_agent = os.getenv("MEDIAWIKI_USER_AGENT", "SDWikiBot (knettel)");

if not token:
	raise EnvironmentError("Bot token not supplied");

async def main():
	tracemalloc.start();
	async with SDWikiBot(
		"sdwikibot!",
		sites=Sites(
			wiki=mwclient.Site("simdemocracy.miraheze.org", clients_useragent=user_agent),
			archives=mwclient.Site("qwrky.dev", path="/mediawiki/", clients_useragent=user_agent)
		),
		tm=tracemalloc,
		intents=discord.Intents.all(),
		activity=discord.Activity(type=discord.ActivityType.watching, name="documents"),
		status=discord.Status.idle
	) as bot:
		await bot.start(token);

if __name__ == "__main__":
	asyncio.run(main());