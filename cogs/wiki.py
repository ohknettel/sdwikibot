import typing
import discord
import time
from discord.ext.commands import Cog
from discord.ext import tasks
from functools import lru_cache
from bot import SDWikiBot
from constants import simdem_navy_blue_colour, EmbedPaginatorView
from utils import chunk_list

class WikiCog(Cog):
    def __init__(self, bot: SDWikiBot):
        self.bot = bot
        self.cache_clear_task.start()

    @lru_cache(maxsize=None)
    def get_page_urls(self) -> typing.Dict[str, str]:
        results = {}
        resp = self.bot.site.get("query", generator="allpages", prop="info", inprop="url", gaplimit="max")
        while True:
            pages = resp["query"]["pages"]
            for page in pages.values():
                results[page["title"]] = page["fullurl"]

            if "continue" in resp:
                resp = self.bot.site.get("query", generator="allpages", prop="info", inprop="url", gaplimit="max", **resp["continue"])
            else:
                break

        return results

    async def interaction_check(self, _: discord.Interaction) -> bool:
        self.page_urls = self.get_page_urls()
        return True

    @discord.app_commands.describe(query="The topic you are searching for.", where="Where to search for this topic.")
    @discord.app_commands.choices(where=[
		discord.app_commands.Choice(name="In titles", value="title"),
		discord.app_commands.Choice(name="In text", value="text")
	])
    @discord.app_commands.command(description="Search for a page.")
    async def search(self, interaction: discord.Interaction, query: str, where: typing.Optional[discord.app_commands.Choice[str]]):
        await interaction.response.defer(thinking=True)

        results = list(self.bot.site.search(query, what=where.value if where else "title", max_items=50))
        if len(results) == 0:
            embed = discord.Embed(
                colour=simdem_navy_blue_colour,
                title=f"\N{left-pointing magnifying glass} Search: `{query}`",
                description="No results were found."
            )
            await interaction.followup.send(embed=embed)
        else:
            chunks = chunk_list([result["title"] for result in results], 10) # pyright: ignore
            paginator = EmbedPaginatorView(interaction.user)
            for index, chunk in enumerate(chunks):
                embed = discord.Embed(
                    colour=simdem_navy_blue_colour,
                    title=f"\N{left-pointing magnifying glass} Search: `{query}`",
                    description=""
                ).set_footer(text=f"Page ({index + 1}/{len(chunks)})")
                assert(embed.description is not None);

                for page in chunk:
                    url = self.page_urls.get(page)

                    if url:
                        embed.description += f"\n- [{page}]({url})"
                    else:
                        embed.description += f"\n- {page}"

                paginator.add_embed(embed)

            if len(paginator.items) <= 1:
                await interaction.followup.send(embed=paginator.items[0])
            else:
                await interaction.followup.send(embed=paginator.items[0], view=paginator)

    @discord.app_commands.command(description="View recent changes.")
    async def recentchanges(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        recentchanges = list(self.bot.site.recentchanges(max_items=50, prop="title|comment|user|timestamp|comments|ids"))
        chunks = chunk_list(recentchanges, 6)
        paginator = EmbedPaginatorView(interaction.user)
        for index, chunk in enumerate(chunks):
            embed = discord.Embed(
                colour=simdem_navy_blue_colour,
                title="Recent changes",
                description=""
            ).set_footer(text=f"Page ({index + 1}/{len(chunks)})")
            assert(embed.description)

            for item in chunk:
                assert isinstance(item, typing.OrderedDict)
                title = item["title"]
                rcid = item["rcid"]
                rctype = item["type"]
                user = item["user"]
                timestamp = item["timestamp"]
                is_page = item["pageid"] != 0
                page_url = self.page_urls.get(title) if is_page else None
                comment = item["comment"]

                formatted_title = title if not is_page else f"[{title}]({page_url})"
                str1 = f"\n- [`{rcid}`] {formatted_title} (<t:{int(time.mktime(timestamp))}:R>)"
                str2 = f"\N{bust in silhouette} **`{user}`** :: `{rctype}` | {comment[:500] + '...' if comment and len(comment) >= 500 else (comment or '**`No comment.`**')}"
                embed.description += "\n".join([str1, str2])

            paginator.add_embed(embed)

        if len(paginator.items) <= 1:
            await interaction.followup.send(embed=paginator.items[0])
        else:
            await interaction.followup.send(embed=paginator.items[0], view=paginator)

    @tasks.loop(hours=1)
    async def cache_clear_task(self):
        self.get_page_urls.cache_clear()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        if not interaction.response.is_done():
            await interaction.response.defer()

        embed = discord.Embed(
            colour=discord.Colour.red(),
            title=f":x: An error occurred",
            description=f"```{error}```"
        )

        await interaction.followup.send(embed=embed)

async def setup(bot: SDWikiBot):
    await bot.add_cog(WikiCog(bot))
