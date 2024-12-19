import discord
from discord import app_commands
from discord.ext import commands
import json
import asyncio
import subprocess
import sys
from dotenv import load_dotenv
import os

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
STATUS_TEXT = os.getenv("BOT_STATUS", "AutoDeleteBot")
CONFIG_FILE = "autodelete_config.json"

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True
activity = discord.CustomActivity(name=STATUS_TEXT)


class AutoDeleteBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=intents, activity=activity)
        self.data_file = CONFIG_FILE
        self.config = self.load_config()

    def load_config(self):
        try:
            with open(self.data_file, "r") as f:
                config = json.load(f)
                self.deleted_message_count = config.get("deleted_message_count", {})
                return config
        except (FileNotFoundError, json.JSONDecodeError):
            self.deleted_message_count = {}
            return {"management_roles": {}}

    def get_management_roles(self, guild_id):
        return self.config.get("management_roles", {}).get(str(guild_id), [])

    def set_management_roles(self, guild_id, role_ids):
        if "management_roles" not in self.config:
            self.config["management_roles"] = {}
        self.config["management_roles"][str(guild_id)] = role_ids
        self.save_config()
        print(json.dumps(self.config, indent=4))

    def save_config(self):
        self.config["deleted_message_count"] = self.deleted_message_count
        with open(self.data_file, "w") as f:
            json.dump(self.config, f, indent=4)

    def get_channel_config(self, channel_id):
        return self.config.get(
            str(channel_id),
            {"limit": None, "pins": False, "embeds": False, "enabled": True},
        )

    def increment_deleted_messages(self, channel_id, count):
        if channel_id not in self.deleted_message_count:
            self.deleted_message_count[channel_id] = 0
        self.deleted_message_count[channel_id] += count
        self.save_config()


bot = AutoDeleteBot()
semaphore = asyncio.Semaphore(3)
autodelete_group = app_commands.Group(name="autodelete", description="Required prefix.")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    if "--restarted" in sys.argv:
        channel_id_arg = next(
            (arg for arg in sys.argv if arg.startswith("--channel=")), None
        )
        message_id_arg = next(
            (arg for arg in sys.argv if arg.startswith("--message=")), None
        )

        if channel_id_arg and message_id_arg:
            channel_id = int(channel_id_arg.split("=")[1])
            message_id = int(message_id_arg.split("=")[1])

            channel = bot.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    embed = discord.Embed(
                        title="Restart Successful",
                        description="The bot has restarted and is now online.",
                        color=discord.Color.green(),
                    )
                    await message.edit(embed=embed)
                except Exception as e:
                    print(f"Failed to edit the restart message: {e}")

        sys.argv.remove("--restarted")
        if channel_id_arg:
            sys.argv.remove(channel_id_arg)
        if message_id_arg:
            sys.argv.remove(message_id_arg)
    await bot.tree.sync()


@bot.event
async def on_message(message):
    if not message.guild:
        return
    if message.author.bot:
        return

    async with semaphore:
        channel_id = str(message.channel.id)
        if channel_id in bot.config:
            channel_config = bot.get_channel_config(channel_id)
            if not channel_config.get("enabled", True):
                return

            limit = channel_config["limit"]
            pins = channel_config["pins"]
            embeds = channel_config["embeds"]

            try:
                messages = []
                async for msg in message.channel.history(limit=(limit + 100)):
                    if not pins and msg.pinned:
                        continue
                    if not embeds and (msg.author.bot and msg.embeds):
                        continue
                    messages.append(msg)
                print(f"{len(messages)} to {limit}")
                if len(messages) >= limit:
                    to_delete = messages[limit:]
                    for msg in to_delete:
                        print(f"Deleting message:{msg.content}")
                        await msg.delete()
                        await asyncio.sleep(0.5)
                    print(
                        f"Deleted {len(to_delete)} messages in {message.channel.name}."
                    )
                    bot.increment_deleted_messages(channel_id, len(to_delete))

            except discord.Forbidden:
                print(
                    f"Missing permissions to manage messages in {message.channel.name}."
                )
            except discord.HTTPException as e:
                print(f"HTTP exception: {e}")


async def check_role(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        embed = discord.Embed(
            title="Invalid",
            description="This command cannot be used here.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
        return False

    required_roles = bot.get_management_roles(guild.id)
    if not required_roles:
        embed = discord.Embed(
            title="Setup",
            description=(
                "No management roles have been set for this server.\n"
                "Use `/autodelete setup` to set roles required to use the bot."
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)
        return False

    if not any(
        discord.utils.get(guild.roles, id=int(role_id)) in interaction.user.roles
        for role_id in required_roles
    ):
        embed = discord.Embed(
            title="Setup",
            description="You don't have any of the required management roles to use this command.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
        return False

    return True


@autodelete_group.command(name="restart", description="Restarts the bot.")
async def restart(interaction: discord.Interaction):
    """Restarts the bot."""
    if not await check_role(interaction):
        return

    embed = discord.Embed(
        title="Restarting",
        description="The bot is restarting... Please wait a moment.",
        color=discord.Color.orange(),
    )
    await interaction.response.defer()
    message = await interaction.followup.send(embed=embed)

    channel_id = interaction.channel.id
    message_id = message.id

    new_argv = (
        [sys.executable]
        + sys.argv
        + ["--restarted", f"--channel={channel_id}", f"--message={message_id}"]
    )

    subprocess.Popen(new_argv, shell=True)

    await bot.close()


@autodelete_group.command(
    name="setup", description="Set the management roles required to use the bot."
)
@app_commands.describe(
    roles="Mention all roles required to manage the bot, separated by spaces."
)
async def setup(interaction: discord.Interaction, roles: str):
    guild = interaction.guild
    if not guild:
        embed = discord.Embed(
            title="Error",
            description="This command must be used in a server.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
        return

    role_ids = []
    for role_str in roles.split():
        if role_str.startswith("<@&") and role_str.endswith(">"):
            try:
                role_id = int(role_str[3:-1])
                role = guild.get_role(role_id)
                if role:
                    role_ids.append(role_id)
            except ValueError:
                pass

    if not role_ids:
        embed = discord.Embed(
            title="Error",
            description="No valid roles were provided.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
        return

    bot.set_management_roles(interaction.guild_id, role_ids)
    embed = discord.Embed(
        title="Roles Set",
        description=f"The following roles have been set: {', '.join([f'<@&{role_id}>' for role_id in role_ids])}",
        color=discord.Color.green(),
    )
    await interaction.response.send_message(embed=embed)


@autodelete_group.command(name="add", description="Add a new task.")
@app_commands.describe(
    channel="The channel to configure.",
    limit="Maximum number of messages allowed.",
    pins="Delete pinned messages.",
    embeds="Delete bot embeds.",
    enabled="Enable or disable the task.",
)
async def add(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    limit: int,
    pins: bool = False,
    embeds: bool = False,
    enabled: bool = True,
):
    if not await check_role(interaction):
        return
    guild = interaction.guild
    bot.config[str(channel.id)] = {
        "limit": limit,
        "pins": pins,
        "embeds": embeds,
        "enabled": enabled,
        "guild": guild.id,
    }
    bot.save_config()
    embed = discord.Embed(
        title="Task added",
        description=(
            f"A task has been added for {channel.mention}.\n\n"
            f"Enabled: `{'Yes' if enabled else 'No'}`\n"
            f"Message Limit: `{limit}`\n"
            f"Delete Pins: `{'Yes' if pins else 'No'}`\n"
            f"Delete Embeds: `{'Yes' if embeds else 'No'}`"
        ),
        color=discord.Color.green(),
    )
    await interaction.response.send_message(embed=embed)


@autodelete_group.command(name="remove", description="Remove a task.")
@app_commands.describe(channel="The channel name the task should be removed from.")
async def remove(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await check_role(interaction):
        return
    if str(channel.id) in bot.config:
        del bot.config[str(channel.id)]
        bot.save_config()
        embed = discord.Embed(
            title="Task removed",
            description=f"A task has been removed for {channel.mention}.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="No task",
            description=f"No task was found for {channel.mention}.",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)


@autodelete_group.command(name="list", description="View all existing tasks.")
async def list(interaction: discord.Interaction):
    if not await check_role(interaction):
        return

    tasks = [
        (channel_id, config)
        for channel_id, config in bot.config.items()
        if channel_id != "management_roles"
        and config.get("guild") == interaction.guild_id
    ]

    if not tasks:
        embed = discord.Embed(
            title="No tasks",
            description="There are no available tasks.\nUse `/autodelete` to `add`, `remove`, or `edit` a task.\nUse `/autodelete help` for a list of commands.",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)
        return

    entries_per_page = 5
    total_pages = (len(tasks) + entries_per_page - 1) // entries_per_page
    current_page = 0

    def create_embed(page):
        start_idx = page * entries_per_page
        end_idx = start_idx + entries_per_page
        page_tasks = tasks[start_idx:end_idx]

        embed = discord.Embed(
            title=f"Tasks (Page {page + 1}/{total_pages})",
            description="Use  `/autodelete` to `add`, `remove`, or `edit` a task.\n\n",
            color=discord.Color.green(),
        )

        for channel_id, config in page_tasks:
            channel = bot.get_channel(int(channel_id))
            if channel:
                task_info = (
                    f"Enabled: `{'Yes' if config.get('enabled', True) else 'No'}`\n"
                    f"Message Limit: `{config.get('limit', 'Not Set')}`\n"
                    f"Delete Pins: `{'Yes' if config.get('pins', False) else 'No'}`\n"
                    f"Delete Embeds: `{'Yes' if config.get('embeds', False) else 'No'}`"
                )
                embed.add_field(
                    name=f"{start_idx + page_tasks.index((channel_id, config)) + 1} - {channel.mention}",
                    value=task_info,
                    inline=False,
                )

        return embed

    embed = create_embed(current_page)
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()

    if total_pages > 1:
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        def check(reaction, user):
            return (
                user == interaction.user
                and str(reaction.emoji) in ["◀️", "▶️"]
                and reaction.message.id == message.id
            )

        while True:
            try:
                reaction, user = await bot.wait_for(
                    "reaction_add", timeout=60.0, check=check
                )

                if str(reaction.emoji) == "◀️" and current_page > 0:
                    current_page -= 1
                elif str(reaction.emoji) == "▶️" and current_page < total_pages - 1:
                    current_page += 1

                await message.edit(embed=create_embed(current_page))
                await message.remove_reaction(reaction.emoji, user)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break


@autodelete_group.command(name="edit", description="Edit an existing task.")
@app_commands.describe(
    channel="The channel whose task you want to edit.",
    limit="The new limit for ",
    pins="Toggle deleting pinned messages.",
    embeds="Toggle deleting bot embeds.",
    enabled="Enable or disable the task.",
)
async def edit(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    limit: int = None,
    pins: bool = None,
    embeds: bool = None,
    enabled: bool = None,
):
    if not await check_role(interaction):
        return

    if str(channel.id) not in bot.config:
        embed = discord.Embed(
            title="Task not found",
            description=f"Coudn't find a task for {channel.mention}.",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)
        return

    if limit is not None:
        bot.config[str(channel.id)]["limit"] = limit
    if pins is not None:
        bot.config[str(channel.id)]["pins"] = pins
    if embeds is not None:
        bot.config[str(channel.id)]["embeds"] = embeds
    if enabled is not None:
        bot.config[str(channel.id)]["enabled"] = enabled

    bot.save_config()
    embed = discord.Embed(
        title="Task updated",
        description=f"The task for {channel.mention} has been updated.\n\n"
        f"Enabled: `{'Yes' if bot.config[str(channel.id)].get('enabled') else 'No'}`\n"
        f"Message Limit: `{bot.config[str(channel.id)].get('limit', 'Unchanged')}`\n"
        f"Delete Pins: `{'Yes' if bot.config[str(channel.id)].get('pins') else 'No'}`\n"
        f"Delete Embeds: `{'Yes' if bot.config[str(channel.id)].get('embeds') else 'No'}`",
        color=discord.Color.green(),
    )
    await interaction.response.send_message(embed=embed)


@autodelete_group.command(
    name="stats", description="View this server's bot statistics."
)
async def stats(interaction: discord.Interaction):
    if not await check_role(interaction):
        return

    server_tasks = []
    for channel_id, config in bot.config.items():
        if (
            channel_id == "management_roles"
            or config.get("guild") != interaction.guild_id
        ):
            continue
        server_tasks.append(config)

    total_tasks = len(server_tasks)
    active_tasks = sum(1 for task in server_tasks if task.get("enabled", True))
    inactive_tasks = total_tasks - active_tasks
    management_roles = bot.get_management_roles(interaction.guild_id)

    if management_roles:
        roles_mentions = ", ".join(f"<@&{role_id}>" for role_id in management_roles)
    else:
        roles_mentions = "None"

    deleted_counts = []
    combined_total = 0
    for channel_id, count in bot.deleted_message_count.items():
        channel = bot.get_channel(int(channel_id))
        if channel and channel.guild.id == interaction.guild_id:
            deleted_counts.append(f"{channel.mention}: `{count}`")
            combined_total += count

    embed = discord.Embed(
        title="Statistics",
        description=(
            f"Total Tasks: `{total_tasks}`\n"
            f"Active Tasks: `{active_tasks}`\n"
            f"Inactive Tasks: `{inactive_tasks}`\n"
            f"Management Roles: {roles_mentions}\n\n"
            f"Deleted Messages per Channel:\n" + "\n".join(deleted_counts) + "\n\n"
            f"Combined Total Deleted Messages: `{combined_total}`"
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=embed)


@autodelete_group.command(
    name="disable", description="Bulk disable all tasks for this server."
)
async def disable(interaction: discord.Interaction):
    await toggle_all(interaction, False)


@autodelete_group.command(
    name="enable", description="Bulk enable all tasks for this server."
)
async def enable(interaction: discord.Interaction):
    await toggle_all(interaction, True)


async def toggle_all(interaction: discord.Interaction, enabled: bool):
    if not await check_role(interaction):
        return

    affected_channels = []
    for channel_id, config in bot.config.items():
        if (
            channel_id == "management_roles"
            or config.get("guild") != interaction.guild_id
        ):
            continue
        bot.config[channel_id]["enabled"] = enabled
        affected_channels.append(channel_id)

    bot.save_config()

    embed = discord.Embed(
        title=f"Tasks {'enabled' if enabled else 'disabled'}",
        description=f"All tasks have been {'`enabled`' if enabled else '`disabled`'} for this server.",
        color=discord.Color.green(),
    )

    await interaction.response.send_message(embed=embed)


@autodelete_group.command(
    name="help", description="Displays a list of all available commands."
)
async def help(interaction: discord.Interaction):
    """Displays a detailed list of all commands."""
    embed = discord.Embed(
        title="Commands",
        description="Here is a list of all available commands:",
        color=discord.Color.green(),
    )

    for command in bot.tree.walk_commands():
        embed.add_field(
            name=f"/{command.qualified_name}",
            value=f"`{command.description}`",
            inline=True,
        )

    await interaction.response.send_message(embed=embed)


@autodelete_group.command(name="purge", description="Purge all tasks for this server.")
async def purge(interaction: discord.Interaction):
    if not await check_role(interaction):
        return

    tasks_to_delete = [
        channel_id
        for channel_id, config in bot.config.items()
        if channel_id != "management_roles"
        and config.get("guild") == interaction.guild_id
    ]

    if not tasks_to_delete:
        embed = discord.Embed(
            title="No tasks",
            description="There are no tasks added for this server.",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)
        return

    class ConfirmPurgeModal(discord.ui.Modal):
        def __init__(self):
            super().__init__(title="Confirm")

            self.add_item(
                discord.ui.TextInput(
                    label="Type 'Y' to proceed. This action cannot be undone.",
                    placeholder="Y",
                    required=True,
                    max_length=10,
                )
            )

        async def on_submit(self, interaction: discord.Interaction):
            if self.children[0].value != "Y":
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="Purge cancelled",
                        description="You did not confirm the action. Task purge has been cancelled.",
                        color=discord.Color.green(),
                    ),
                    ephemeral=True,
                )
                return

            for channel_id in tasks_to_delete:
                del bot.config[channel_id]

            bot.save_config()

            success_embed = discord.Embed(
                title="Purge finished",
                description="All tasks for this server have been successfully purged.",
                color=discord.Color.red(),
            )

            await interaction.response.send_message(embed=success_embed)

    await interaction.response.send_modal(ConfirmPurgeModal())


bot.tree.add_command(autodelete_group)

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
else:
    print("Error: DISCORD_TOKEN is not set in the .env file.")
