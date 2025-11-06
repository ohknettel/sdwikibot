from bot import SDWB2
from discord.ext import commands
import textwrap

class MiscCog(commands.Cog):
	def __init__(self, bot: SDWB2):
		self.bot = bot

	@commands.hybrid_command(description="View the syntax of SD Wikibot.")
	async def syntax(self, ctx: commands.Context):
		await ctx.reply(textwrap.dedent("""
`[[...]]` - searchs all enabled wikis for pages with ... in their title
`[[...#A]]` - searchs all enabled wikis for pages with ... in their title, then grabs the segment with an ID of `A` where available
`[[...#A->B]]` - searchs all enabled wikis for pages with ... in their title, then grabs the contents of the entire segment from a section with ID `A` to the section with ID `B` where available
`[[...#A#B#C]]` - searchs all enabled wikis for pages with ... in their title, then grabs the contents of segments `A`, `B` and `C` through their ID
`[[...|A]]` - alternative syntax for above
**Fetching segments by ID is case-insensitive.**"""))

	@commands.hybrid_command(description="Help about SD Wikibot.")
	async def help(self, ctx: commands.Context):
		await ctx.reply(textwrap.dedent("""
Hi! I can fetch links and segments from configured wiki sites using double bracket notation.

**Usage:**
`[[search term]]` - Fetches links about "search term" from all enabled wikis

**Examples:**
- `[[SD v Yt7iju 2025 Crim 102s]]` - Gets link for SD v Yt7iju 2025 Crim 102
- `[[in re]]` - Gets links for all pages starting with "in re"
- `[[Criminal Code]]` - Gets links for all pages with "Criminal Code" in their title
_View advanced examples & more using </syntax:1401975282352521257>_

**Tips:**
- Use specific titles for better results
- Check spelling - exact matches work best
- Some articles may not be available on all configured wikis

Type your search term in double brackets to get started!"""))

async def setup(bot: SDWB2):
	await bot.add_cog(MiscCog(bot))