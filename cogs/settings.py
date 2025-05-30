from discord.ext.commands import Cog;
from bot import SDWikiBot;
from constants import neutral_colour;
import discord;

def get_param_type(entry: dict):
	if isinstance(entry.get("default"), bool) or entry.get("display") == "yesno":
		return bool;
	return str;

class SettingsCog(Cog):
	group = discord.app_commands.Group(name="settings", description="Configure the bot.");
	def __init__(self, bot: SDWikiBot):
		self.bot = bot;
		self._set = discord.app_commands.Group(name="set", description="Set the value of a setting.");
		self.group.add_command(self._set);

	async def cog_load(self):
		schema, _ = self.bot._return_settings();
		for _, items in schema.items():
			for item in items:
				name = item["name"];

				if name == "toggle_smart_referencing":
					continue;

				description = item["description"];
				param_type = get_param_type(item);

				def command_cb_factory(cmd_name):
					async def command_cb(interaction: discord.Interaction, value):
						if not interaction.response.is_done():
								await interaction.response.defer(thinking=True);

						assert interaction.guild;
						guild_id = interaction.guild.id;
						settings = self.bot.get_guild_settings(guild_id);
						try:
							settings[cmd_name] = value;
							self.bot.sync_guild_settings(guild_id);

							embed = discord.Embed(
								colour=discord.Colour.green(),
								title=f":white_check_mark: Success",
								description=f"Succesfully set `{cmd_name}` to `{value}`."
							);
							await interaction.followup.send(embed=embed);
						except Exception as e:
							embed = discord.Embed(
								colour=discord.Colour.red(),
								title=f":x: Error",
								description=f"Could not set `{cmd_name}` to `{value}`:\n```{e}```"
							);
							await interaction.followup.send(embed=embed);

					annotations = {"interaction": discord.Interaction, "value": param_type};
					command_cb.__annotations__ = annotations;
					command_cb.__name__ = f"set_{cmd_name}";
					return command_cb;

				app_cmd = discord.app_commands.Command(name=name,
					description=f"Sets {description.lower()}",
					callback=command_cb_factory(name));

				self._set.add_command(app_cmd, override=True);

	async def interaction_check(self, interaction: discord.Interaction):
		assert(self.bot.application);
		if not interaction.guild:
			return False;

		member = interaction.guild.get_member(interaction.user.id);
		if not member:
			return False;
		elif not member.guild_permissions.manage_guild \
			and not member.id == self.bot.application.owner.id:
			raise discord.app_commands.MissingPermissions([]);

		return True;

	@group.command(description="Toggles smart referencing on and off.")
	async def toggle_smart_referencing(self, interaction: discord.Interaction, toggle: bool):
		if not interaction.response.is_done():
			await interaction.response.defer(thinking=True);
		
		assert(interaction.guild);
		settings = self.bot.get_guild_settings(interaction.guild.id);
		settings["toggle_smart_referencing"] = toggle;
		self.bot.sync_guild_settings(interaction.guild.id);
		embed = discord.Embed(
			colour=discord.Colour.green(),
			title=f":white_check_mark: Success",
			description=f"Toggled smart referencing {'on' if toggle else 'off'}."
		);
		await interaction.followup.send(embed=embed);

	@group.command(name="list", description="Lists the current configuration of the bot.")
	async def _list(self, interaction: discord.Interaction):
		await interaction.response.defer(thinking=True);
		assert(interaction.guild);
		settings = self.bot.get_guild_settings(interaction.guild.id);
		
		embed = discord.Embed(
			colour=neutral_colour,
			title=f":gear: Settings{': **`' + interaction.guild.name + '`**' if interaction.guild else ''}".strip()
		).set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None);

		metadata = settings["metadata"];
		for category, items in metadata.items():
			description = "";
			for item in items:
				name = item["name"];
				item_description = item["description"];
				value = settings[name];
				if (display := item.get("display")):
					if display == "yesno":
						value = "Yes" if value else "No";

				description += f"\n\n**`{name}`** ({value})\n_{item_description}_";
			embed.add_field(name=category.replace("_", " ").capitalize(), value=description.strip(), inline=False);

		await interaction.followup.send(embed=embed);

async def setup(bot: SDWikiBot):
	await bot.add_cog(SettingsCog(bot));