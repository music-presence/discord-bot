import math
import os
import dotenv
import dataclasses
import discord
import traceback
import asyncio
import secrets

import enums
import objects
from objects.macro_embed import MacroEmbed
from objects.macro_create_modal import MacroCreate, MacroEdit
import utils

from dateutil.parser import isoparse
from datetime import timezone
from asyncio import Semaphore, gather

from time import time
from typing import Optional
from discord import app_commands as discord_command
from reactionmenu import ViewMenu, ViewButton

from enums.constants import (
    HELP_TROUBLESHOOTING_URLS,
    ROLE_BETA_TESTER,
    ROLES_OS,
)
from utils.init_database import load_macros_database, load_settings_database
from utils.macros_database import (
    delete_macro,
    get_macro,
    macros_list,
)

# Required permissions:
# - Manage Roles (required to set and remove roles from members)
# - Use Slash Commands (required to create and register commands in guilds)
# Invite link:
# https://discord.com/api/oauth2/authorize?client_id=1236022326773022800&permissions=2415919104&scope=bot%20applications.commands


# ------------------------------------- GLOBAL INITS
dotenv.load_dotenv()

settings = load_settings_database()
macros = load_macros_database("macros.db")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.presences = True
intents.message_content = True

discord.utils.setup_logging()
discord.VoiceClient.warn_nacl = (
    False  # doesn't need voice perms, it's a role assign bot
)
client = discord.Client(intents=intents)

tree = discord_command.CommandTree(client)

bot_utils = utils.BotUtils(client, macros, settings, tree)


# ------------------------------------- EVENTS
# TODO properly remove roles from users when the bot is shut down
@client.event
async def on_ready():
    for guild in client.guilds:
        await bot_utils.setup_guild(guild)
    client.loop.create_task(bot_utils.update_apps_periodically())


@client.event
async def on_guild_join(guild: discord.Guild):
    await bot_utils.setup_guild(guild)


@client.event
async def on_guild_remove(guild: discord.Guild):
    if settings.dexists(enums.SettingsKeys.ROLES, str(guild.id)):
        settings.dpop(enums.SettingsKeys.ROLES, str(guild.id))


@client.event
async def on_presence_update(_: discord.Member, member: discord.Member):
    await bot_utils.check_member(member)


@client.event
async def on_message(message: discord.Message):
    if message.author.id == client.user.id:
        return

    await bot_utils.autolog(message)


@tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
):
    command_name = (
        interaction.command.parent.name
        if interaction.command and interaction.command.parent
        else interaction.command.name if interaction.command else None
    )

    if command_name == enums.Command.JOINED:
        if isinstance(error, discord.app_commands.errors.TransformerError):
            await interaction.response.send_message(
                "❌ Could not find that member in the server.", ephemeral=True
            )
            return

    if command_name in (enums.Command.MACRO, enums.Command.MACROS):
        if isinstance(error, discord.app_commands.errors.MissingAnyRole):
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

    print("Unhandled command error:", error)
    traceback.print_exc()

    try:
        await interaction.response.send_message(
            "An unexpected error occurred while executing this command.",
            ephemeral=True,
        )
    except discord.NotFound:
        pass
    except discord.InteractionResponded:
        try:
            await interaction.followup.send(
                "An unexpected error occurred while executing this command.",
                ephemeral=True,
            )
        except Exception:
            pass


# Technically we should observe updates to roles
# that the listener roles depend on too but that happens so infrequently,
# we might as well wait until the presence has been updated.


# ------------------------------------- COMMANDS
@tree.command(name=enums.Command.ROLE, description=enums.Command.ROLE.description())
async def command_set_role(
    interaction: discord.Interaction,
    for_role: Optional[discord.Role],
    listener_role: Optional[discord.Role],
    summary: Optional[bool],
):
    global settings

    if interaction.guild_id is None:
        return await interaction.response.send_message("No guild ID for interaction")

    if not for_role and listener_role:
        return await interaction.response.send_message(
            "Need a role to set the listener role for"
        )

    is_reset = not listener_role
    guild_id = str(interaction.guild.id)
    if not settings.dexists(enums.SettingsKeys.ROLES, guild_id):
        if is_reset:
            return await interaction.response.send_message(
                "No listener roles configured"
            )
        settings.dadd(enums.SettingsKeys.ROLES, (guild_id, {}))

    if is_reset and not for_role:
        await bot_utils.remove_all_listener_roles_from_all(interaction.guild)
        settings.dpop(enums.SettingsKeys.ROLES, str(interaction.guild.id))
        return await interaction.response.send_message(
            "Removed all listener roles from all members"
        )

    guild_roles = settings.dget(enums.SettingsKeys.ROLES, guild_id)
    if is_reset and for_role:
        if str(for_role.id) in guild_roles:
            listener_role = await bot_utils.clear_role_listener_of_role(
                interaction.guild, for_role
            )
            listener_role_id = guild_roles[str(for_role.id)]
            assert listener_role is not None and listener_role.id == listener_role_id
            del guild_roles[str(for_role.id)]
            settings.dadd(enums.SettingsKeys.ROLES, (guild_id, guild_roles))
            return await interaction.response.send_message(
                f"Disabled monitoring for <@&{for_role.id}> "
                f"and removed the <@&{listener_role_id}> role from all members",
                allowed_mentions=discord.AllowedMentions(roles=False),
            )
        else:
            return await interaction.response.send_message(
                f"No listener role configured for role <@&{for_role.id}>",
                allowed_mentions=discord.AllowedMentions(roles=False),
            )

    if str(listener_role.id) in guild_roles:
        return await interaction.response.send_message(
            f"Cannot use <@&{listener_role.id}> as a listener role. "
            "It is already used as a requirement for a listener role",
            allowed_mentions=discord.AllowedMentions(roles=False),
        )

    for other_listener_role_id in guild_roles.values():
        if for_role.id == other_listener_role_id:
            return await interaction.response.send_message(
                f"Cannot use <@&{for_role.id}> as a requirement for a listener role. "
                "It is already used as a listener role",
                allowed_mentions=discord.AllowedMentions(roles=False),
            )

    if not listener_role.is_assignable():
        return await interaction.response.send_message(
            "Cannot assign this role to server members. "
            "Make sure the bot's role is above the specified role"
        )

    if not listener_role.permissions.is_subset(discord.Permissions.none()):
        return await interaction.response.send_message(
            "Only roles without any extra permissions are allowed"
        )

    guild_roles[str(for_role.id)] = listener_role.id
    settings.dadd(enums.SettingsKeys.ROLES, (guild_id, guild_roles))
    await interaction.response.send_message(
        f"Listener role for <@&{for_role.id}> is now <@&{listener_role.id}>"
        + (f"\n{bot_utils.get_role_overview(interaction.guild)}" if summary else ""),
        allowed_mentions=discord.AllowedMentions(roles=False),
    )
    await bot_utils.check_guild(interaction.guild)


@tree.command(name=enums.Command.ROLES, description=enums.Command.ROLES.description())
async def command_list_roles(interaction: discord.Interaction):
    if not settings.dexists(enums.SettingsKeys.ROLES, str(interaction.guild.id)):
        return await interaction.response.send_message(
            "No listener roles configured for this server"
        )

    overview = bot_utils.get_role_overview(interaction.guild)
    await interaction.response.send_message(
        overview,
        allowed_mentions=discord.AllowedMentions(roles=False),
    )


@tree.command(name=enums.Command.JOINED, description=enums.Command.JOINED.description())
@discord_command.describe(member="The member to check (leave empty to check yourself)")
async def command_joined_stats(
    interaction: discord.Interaction, member: discord.Member = None
):
    target_member = member or interaction.user
    guild = interaction.guild
    members_by_join_date = sorted(
        [member for member in guild.members if not member.bot],
        key=lambda m: m.joined_at or discord.utils.utcnow(),
    )

    try:
        member_index = members_by_join_date.index(target_member)
    except ValueError:
        await interaction.response.send_message(
            f"❌ Could not find {'yourself' if member is None else target_member.display_name} in the member list.",
            ephemeral=True,
        )
        return

    member_number = member_index + 1
    total_members = len(members_by_join_date)
    join_date = "Unknown"
    if target_member.joined_at:
        join_date = target_member.joined_at.strftime("%B %d, %Y")

    embed = discord.Embed(
        title="Member Timeline Position", color=0xE6DFD0  # Presence Beige:tm:
    )
    if member:
        embed.description = (
            f"**{target_member.display_name}** joined this server on **{join_date}**"
        )
        embed.add_field(
            name="Member Number",
            value=f"#{member_number} out of {total_members}",
            inline=False,
        )
    else:
        embed.description = f"You joined this server on **{join_date}**"
        embed.add_field(
            name="Your Member Number",
            value=f"#{member_number} out of {total_members}",
            inline=False,
        )

    if target_member.display_avatar:
        embed.set_thumbnail(url=target_member.display_avatar.url)

    percentage = 0
    if total_members > 1:
        percentage = round(
            ((total_members - member_number) / (total_members - 1)) * 100, 1
        )

    embed.add_field(
        name="Early Bird Percentage",
        value=f"You joined earlier than {percentage}% of members",
        inline=True,
    )
    embed.set_footer(
        text=f"{guild.name} • Server created on {guild.created_at.strftime('%B %d, %Y')}"
    )

    await interaction.response.send_message(embed=embed)

from enums.constants import ROLE_BETA_TESTER, ROLES_OS

@tree.command(name=enums.Command.INFO, description=enums.Command.INFO.description())
@discord_command.describe(member="The member to check (leave empty to check yourself)")
async def command_info(interaction: discord.Interaction, member: discord.Member = None):
    target_member = member or interaction.user
    guild = interaction.guild
    members_by_join_date = sorted(
        [m for m in guild.members if not m.bot],
        key=lambda m: m.joined_at or discord.utils.utcnow(),
    )

    try:
        member_index = members_by_join_date.index(target_member)
    except ValueError:
        await interaction.response.send_message(
            f"❌ Could not find {'you' if member is None else target_member.display_name} in the member list.",
            ephemeral=True,
        )
        return

    member_number = member_index + 1
    total_members = len(members_by_join_date)
    join_date = target_member.joined_at.strftime("%B %d, %Y") if target_member.joined_at else "Unknown"

    # --- Join Info ---
    
    embed = discord.Embed(
        title="Member Information",
        color=0xE6DFD0,
        description=f"{'You' if member is None else f'**{target_member.display_name}**'} joined this server on **{join_date}**"
    )
    embed.add_field(name="Member Number", value=f"#{member_number} out of {total_members}", inline=False)

    percentage = round(((total_members - member_number) / (total_members - 1)) * 100, 1) if total_members > 1 else 0
    embed.add_field(
        name="Early Bird Percentage",
        value=f"You joined earlier than {percentage}% of members",
        inline=True,
    )

    # force a new line if no sponsor field will be added
    status = bot_utils.get_sponsor_status(target_member)
    if status is None:
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
    # --- Sponsor Info ---
    if status is not None:
        sponsor_type = "Monthly" if status["type"] == "subscription" else "One Time"
        platforms_display = ", ".join(
            f"{p['emoji']} [{p['name']}]({p['url']})" if p.get("url") else f"{p['emoji']} {p['name']}"
            for p in status["platforms"]
        )
        embed.add_field(name="Sponsorship", value=f"{sponsor_type} sponsor ({platforms_display})", inline=False)

    # --- OS Platform Info ---
    os_roles = [guild.get_role(rid) for rid in ROLES_OS]
    os_roles = [r for r in os_roles if r is not None and r in target_member.roles]
    if os_roles:
        platforms_value = ", ".join(f"{r.mention}" for r in os_roles)
    else:
        platforms_value = "None"
    embed.add_field(name="Platform(s)", value=platforms_value, inline=True)

    # --- Beta Tester Info ---
    beta_tester_role = guild.get_role(ROLE_BETA_TESTER)
    is_beta = beta_tester_role and beta_tester_role in target_member.roles
    embed.add_field(name="Beta Tester", value="✅ Yes" if is_beta else "❌ No", inline=True)

    if target_member.display_avatar:
        embed.set_thumbnail(url=target_member.display_avatar.url)

    embed.set_footer(text=f"{guild.name} • Server created on {guild.created_at.strftime('%B %d, %Y')}")

    await interaction.response.send_message(embed=embed)

@tree.command(
    name=enums.Command.DATEROLE, description=enums.Command.DATEROLE.description()
)
@discord_command.describe(
    from_date="ISO format date (YYYY-MM-DD or YYYY-MM-DDTHH:MM)", role="Role to assign"
)
async def command_date_role(
    interaction: discord.Interaction, from_date: str, role: discord.Role
):
    """
    Assign a role to all members who joined after the given ISO date.
    """
    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        parsed = isoparse(from_date)
    except ValueError:
        return await interaction.followup.send(
            "❌ Invalid date format. Use ISO 8601 like `2025-07-01` or `2025-07-01T15:30`.",
            ephemeral=True,
        )

    parsed = parsed.astimezone(timezone.utc)

    bot_member = interaction.guild.me
    if role >= bot_member.top_role:
        return await interaction.followup.send(
            f"❌ Cannot assign {role.mention}. The role is higher than the bot's top role.",
            ephemeral=True,
        )

    sem = Semaphore(1)

    async def try_add_role(member):
        async with sem:
            if role not in member.roles:
                try:
                    await member.add_roles(role)
                    return True
                except discord.Forbidden:
                    return None
            return False

    tasks = [
        try_add_role(member)
        for member in interaction.guild.members
        if not member.bot
        and member.joined_at
        and member.joined_at.astimezone(timezone.utc) >= parsed
    ]

    results = await gather(*tasks)
    count = sum(1 for result in results if result)

    await interaction.followup.send(
        f"✅ Gave {role.mention} to {count} member{'s' if count != 1 else ''} who joined after <t:{int(parsed.timestamp())}:f>",
        allowed_mentions=discord.AllowedMentions(roles=False),
        ephemeral=True,
    )


@tree.command(
    name=enums.Command.LISTENING, description=enums.Command.LISTENING.description()
)
async def command_listening_role(
    interaction: discord.Interaction, delete: Optional[bool]
):
    guild_member = None
    for member in interaction.guild.members:
        if member.id == interaction.user.id:
            guild_member = member
            break

    if guild_member is None:
        return await interaction.response.send_message(
            "Interaction user not found amongst guild members"
        )

    user_id = guild_member.id
    if delete:
        settings.dpop(enums.SettingsKeys.USER_APPS, str(user_id))
        await bot_utils.check_member(guild_member)
        await interaction.response.send_message(
            f"Removed any registered app IDs for <@{user_id}>"
        )
        return

    count = 0
    for activity in guild_member.activities:
        if (
            not isinstance(activity, discord.Spotify)
            and isinstance(activity, discord.Activity)
            and activity.type == discord.ActivityType.listening
        ):
            app_id = activity.application_id
            if app_id is None:
                continue

            if settings.dexists(enums.SettingsKeys.APPS, str(app_id)):
                await interaction.response.send_message(
                    f"App ID `{app_id}` is already known"
                )
                return

            if not settings.dexists(enums.SettingsKeys.USER_APPS, str(user_id)):
                settings.dadd(enums.SettingsKeys.USER_APPS, (str(user_id), {}))

            user_apps = settings.dget(enums.SettingsKeys.USER_APPS, str(user_id))
            # Only one custom app ID is allowed per user.
            user_apps.clear()
            user_apps[str(app_id)] = dataclasses.asdict(
                objects.UserApp(app_id, user_id=guild_member.id, timestamp=int(time()))
            )
            settings.dadd(enums.SettingsKeys.USER_APPS, (str(user_id), user_apps))
            await interaction.response.send_message(
                f"Registered listening role for app ID `{app_id}` for <@{user_id}>"
            )
            count += 1

    if count == 0:
        return await interaction.response.send_message(
            f"No app ID found, make sure your presence is visible"
        )

    await bot_utils.check_member(guild_member)


@tree.command(name=enums.Command.STOP, description=enums.Command.STOP.description())
async def command_stop(interaction: discord.Interaction):
    for guild in client.guilds:
        await bot_utils.remove_all_listener_roles_from_all(guild)

    await interaction.response.send_message("Removed all roles, stopping now")
    await client.close()

    settings._autodumpdb()


@tree.command(name=enums.Command.LOGS, description=enums.Command.LOGS.description())
@discord_command.choices(
    os=[
        discord_command.Choice(name="Windows", value=enums.Platform.WIN),
        discord_command.Choice(name="Mac", value=enums.Platform.MAC),
        discord_command.Choice(name="Linux", value=enums.Platform.LIN),
    ]
)
async def command_logs(
    interaction: discord.Interaction, os: discord_command.Choice[str] = None
):
    await bot_utils.logs_response_to_interaction(
        interaction, os.value if os is not None else None
    )


@tree.command(name=enums.Command.HELP, description=enums.Command.HELP.description())
@discord_command.choices(
    topic=[
        discord_command.Choice(
            name=enums.HelpTopic.INSTALL, value=enums.HelpTopic.INSTALL
        ),
        discord_command.Choice(
            name=enums.HelpTopic.PLAYER_DETECTION,
            value=enums.HelpTopic.PLAYER_DETECTION,
        ),
        discord_command.Choice(
            name=enums.HelpTopic.APP_LOGS, value=enums.HelpTopic.APP_LOGS
        ),
    ]
)
async def command_help(
    interaction: discord.Interaction, topic: discord_command.Choice[str] = None
):
    value = enums.HelpTopic(topic.value) if topic is not None else None
    view = discord.utils.MISSING
    if value == enums.HelpTopic.INSTALL:
        try:
            view = objects.LinkButtons(await bot_utils.get_download_urls())
        except Exception as e:
            return await interaction.response.send_message(f"An error occurred: {e}")

    elif value == enums.HelpTopic.PLAYER_DETECTION:
        view = objects.LinkButtons(HELP_TROUBLESHOOTING_URLS)

    elif value == enums.HelpTopic.APP_LOGS:
        return await bot_utils.logs_response_to_interaction(interaction)

    await interaction.response.send_message(
        bot_utils.get_help_message(value), view=view
    )


@tree.command(
    name=enums.Command.TESTER_COVERAGE,
    description=enums.Command.TESTER_COVERAGE.description(),
)
async def command_tester_coverage(interaction: discord.Interaction):
    guild = interaction.guild
    beta_tester_role = guild.get_role(ROLE_BETA_TESTER)
    if beta_tester_role is None:
        return await interaction.response.send_message(
            "Beta tester role not found. :thinking:"
        )
    elif len(beta_tester_role.members) == 0:
        return await interaction.response.send_message(
            "No beta testers found yet ! :confused:"
        )

    os_roles = []
    for role_id in ROLES_OS:
        role = guild.get_role(role_id)
        if role is not None:
            os_roles.append(role)
    if len(os_roles) == 0:
        return await interaction.response.send_message("No OS roles found. :thinking:")

    coverage = bot_utils.tester_coverage_compute(beta_tester_role, os_roles)
    embed = bot_utils.tester_coverage_make_embed(beta_tester_role, os_roles, coverage)

    await interaction.response.send_message(embed=embed)


@tree.command(
    name=enums.Command.MACRO,
    description=enums.Command.MACRO.description(),
)
async def macro(
    interaction: discord.Interaction,
    name: str,
    message: str | None,
):
    macro = get_macro(bot_utils.macros_db, name)

    if macro is not None:
        await interaction.response.send_message(
            content=message, embed=MacroEmbed(macro).show_embed()
        )
    else:
        await interaction.response.send_message(
            f"Macro with name `{name}` not found.", ephemeral=True
        )


macros_group = discord_command.Group(
    name=enums.Command.MACROS,
    description=enums.Command.MACROS.description(),
)


@macros_group.command(
    name=enums.Command.MACROS_CREATE,
    description=enums.Command.MACROS_CREATE.description(),
)
async def create(interaction: discord.Interaction, name: str):
    if get_macro(bot_utils.macros_db, name) is None:
        await interaction.response.send_modal(
            MacroCreate(macro_name=name, macros_db=bot_utils.macros_db)
        )
    else:
        await interaction.response.send_message(
            f"Macro with name `{name}` already exists!", ephemeral=True
        )
    bot_utils.update_macros_cache()


@macros_group.command(
    name=enums.Command.MACROS_EDIT,
    description=enums.Command.MACROS_EDIT.description(),
)
async def edit(interaction: discord.Interaction, name: str):
    macro = get_macro(bot_utils.macros_db, name)

    await interaction.response.send_modal(
        MacroEdit(macro=macro, macros_db=bot_utils.macros_db)
    )
    bot_utils.update_macros_cache()


@macros_group.command(
    name=enums.Command.MACROS_LIST,
    description=enums.Command.MACROS_LIST.description(),
)
async def list_macros(interaction: discord.Interaction):
    macros = macros_list(bot_utils.macros_db)
    menu = ViewMenu(
        interaction,
        menu_type=ViewMenu.TypeEmbedDynamic,
        rows_requested=10,
        custom_embed=discord.Embed(
            color=discord.Color.from_str("#b3a089"), title="Available Macros"
        ),
        timeout=300,  # 5 minutes
    )

    if macros:
        for macro in macros:
            menu.add_row(
                f"`{macro.name}` by <@{macro.creator}> - last edited <t:{math.floor(macro.date_edited)}:f>"
            )

        menu.add_button(ViewButton.go_to_first_page())
        menu.add_button(ViewButton.back())
        menu.add_button(ViewButton.next())
        menu.add_button(ViewButton.go_to_last_page())

        await menu.start()
    else:
        await interaction.response.send_message("There are no macros!", ephemeral=True)


@macros_group.command(
    name=enums.Command.MACROS_DELETE,
    description=enums.Command.MACROS_DELETE.description(),
)
async def remove(interaction: discord.Interaction, name: str):
    if delete_macro(bot_utils.macros_db, name) == 1:
        await interaction.response.send_message(
            f"Macro `{name}` removed", ephemeral=True
        )

        bot_utils.update_macros_cache()
    else:
        await interaction.response.send_message(
            f"Macro `{name}` either not removed or doesn't exist", ephemeral=True
        )


@edit.autocomplete("name")
@remove.autocomplete("name")
@macro.autocomplete("name")
async def macro_autocomplete(
    _: discord.Interaction, current: str
) -> list[discord_command.Choice[str]]:
    if current is None or current == "":
        return [
            discord_command.Choice(name=macro_name, value=macro_name)
            for macro_name in bot_utils.macros_cache
        ][:25]
    else:
        return [
            discord_command.Choice(name=macro_name, value=macro_name)
            for macro_name in bot_utils.search_macros(current)
        ]


tree.add_command(macros_group)

sponsor_group = discord_command.Group(
    name=enums.Command.SPONSOR,
    description=enums.Command.SPONSOR.description(),
)


platform_group = discord_command.Group(
    name=enums.Command.SPONSOR_PLATFORM,
    description=enums.Command.SPONSOR_PLATFORM.description(),
    parent=sponsor_group,
)


@platform_group.command(
    name=enums.Command.SPONSOR_PLATFORM_ADD,
    description=enums.Command.SPONSOR_PLATFORM_ADD.description(),
)
async def sponsor_platform_add(
        interaction: discord.Interaction, name: str, emoji: str, role: discord.Role,  url: Optional[str] = None,
):
    guild_id = str(interaction.guild.id)

    if not settings.dexists(enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id):
        settings.dadd(enums.SettingsKeys.SPONSOR_PLATFORMS, (guild_id, {}))

    if not settings.dexists(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id):
        settings.dadd(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, (guild_id, {}))

    platforms = settings.dget(enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id)
    platforms[name] = {"emoji": emoji, "url": url}
    settings.dadd(enums.SettingsKeys.SPONSOR_PLATFORMS, (guild_id, platforms))

    role_map = settings.dget(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id)
    role_map[str(role.id)] = name
    settings.dadd(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, (guild_id, role_map))

    await interaction.response.send_message(
        f"Platform `{name}` set to {emoji} for {role.mention}"
        + (f" ([Link]({url}))" if url else ""),
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions(roles=False),
    )


@platform_group.command(
    name=enums.Command.SPONSOR_PLATFORM_EDIT,
    description=enums.Command.SPONSOR_PLATFORM_EDIT.description(),
)
async def sponsor_platform_edit(
    interaction: discord.Interaction,
    name: str,
    emoji: Optional[str] = None,
    role: Optional[discord.Role] = None,
    url: Optional[str] = None,
):
    guild_id = str(interaction.guild.id)

    if not settings.dexists(enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id):
        return await interaction.response.send_message(
            "No platforms configured", ephemeral=True
        )

    platforms = settings.dget(enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id)
    if name not in platforms:
        return await interaction.response.send_message(
            f"Platform `{name}` not found", ephemeral=True
        )

    if isinstance(platforms[name], str):  # legacy format migration
        platforms[name] = {"emoji": platforms[name], "url": None}

    if emoji:
        platforms[name]["emoji"] = emoji
    if url is not None:
        platforms[name]["url"] = url  # allow clearing with empty string

    settings.dadd(enums.SettingsKeys.SPONSOR_PLATFORMS, (guild_id, platforms))

    if role is not None:
        if not settings.dexists(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id):
            settings.dadd(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, (guild_id, {}))

        role_map = settings.dget(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id)
        for rid, plat in list(role_map.items()):
            if plat == name:
                del role_map[rid]
        role_map[str(role.id)] = name
        settings.dadd(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, (guild_id, role_map))

    await interaction.response.send_message(
        f"Platform `{name}` updated",
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions(roles=False),
    )


@platform_group.command(
    name=enums.Command.SPONSOR_PLATFORM_DELETE,
    description=enums.Command.SPONSOR_PLATFORM_DELETE.description(),
)
async def sponsor_platform_delete(interaction: discord.Interaction, name: str):
    guild_id = str(interaction.guild.id)

    if not settings.dexists(enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id):
        return await interaction.response.send_message(
            "No platforms configured", ephemeral=True
        )

    platforms = settings.dget(enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id)
    if name not in platforms:
        return await interaction.response.send_message(
            f"Platform `{name}` not found", ephemeral=True
        )

    del platforms[name]
    settings.dadd(enums.SettingsKeys.SPONSOR_PLATFORMS, (guild_id, platforms))

    if settings.dexists(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id):
        role_map = settings.dget(
            enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id
        )
        to_del = [rid for rid, n in role_map.items() if n == name]
        for rid in to_del:
            del role_map[rid]
        settings.dadd(
            enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, (guild_id, role_map)
        )

    await interaction.response.send_message(
        f"Platform `{name}` deleted", ephemeral=True
    )
@platform_group.command(
    name=enums.Command.SPONSOR_PLATFORM_LIST,
    description=enums.Command.SPONSOR_PLATFORM_LIST.description(),
)
async def sponsor_platform_list(interaction: discord.Interaction):
    overview = bot_utils.get_platform_overview(interaction.guild)
    if overview is None:
        return await interaction.response.send_message(
            "No platforms configured", ephemeral=True
        )
    await interaction.response.send_message(
        overview,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions(roles=False),
    )
@sponsor_platform_edit.autocomplete("name")
@sponsor_platform_delete.autocomplete("name")
async def sponsor_platform_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[discord_command.Choice[str]]:
    if current is None or current == "":
        names = bot_utils.get_platform_names(interaction.guild)
    else:
        names = bot_utils.search_platforms(interaction.guild, current)
    return [discord_command.Choice(name=n, value=n) for n in names][:25]


@sponsor_group.command(
    name=enums.Command.SPONSOR_SUBROLES,
    description=enums.Command.SPONSOR_SUBROLES.description(),
)
async def sponsor_subroles(
    interaction: discord.Interaction,
    monthly_role: Optional[discord.Role],
    normal_role: Optional[discord.Role],
):
    guild_id = str(interaction.guild.id)

    if not settings.dexists(enums.SettingsKeys.SPONSOR_ROLES, guild_id):
        settings.dadd(enums.SettingsKeys.SPONSOR_ROLES, (guild_id, {}))

    roles_cfg = settings.dget(enums.SettingsKeys.SPONSOR_ROLES, guild_id)

    if monthly_role:
        roles_cfg["monthly"] = monthly_role.id
    if normal_role:
        roles_cfg["normal"] = normal_role.id

    settings.dadd(enums.SettingsKeys.SPONSOR_ROLES, (guild_id, roles_cfg))

    await interaction.response.send_message(
        "Sponsor roles updated", ephemeral=True,
        allowed_mentions=discord.AllowedMentions(roles=False),
    )

@sponsor_group.command(
    name=enums.Command.SPONSOR_INFO,
    description=enums.Command.SPONSOR_INFO.description(),
)
@discord_command.describe(member="Member to check (defaults to yourself)")
async def sponsor_info(
    interaction: discord.Interaction, member: Optional[discord.Member] = None
):
    target = member or interaction.user
    status = bot_utils.get_sponsor_status(target)

    if status is None:
        return await interaction.response.send_message(
            f"{target.mention} is not marked as a sponsor.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions(users=False),
        )

    sponsor_type = (
        "Monthly" if status["type"] == "subscription" else "One Time"
    )
    platforms_display = ", ".join(
        (f"{p['emoji']} [{p['name']}]({p['url']})" if p.get("url") else f"{p['emoji']} {p['name']}")
        for p in status["platforms"]
    )

    await interaction.response.send_message(
        f"{target.mention}: {sponsor_type} sponsor ({platforms_display})",
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions(users=False),
        suppress_embeds=True,
    )
@sponsor_group.command(
    name=enums.Command.SPONSOR_LIST,
    description=enums.Command.SPONSOR_LIST.description(),
)
async def sponsor_list(interaction: discord.Interaction):
    overview = bot_utils.get_sponsor_list(interaction.guild)
    if overview is None:
        return await interaction.response.send_message(
            "No sponsor roles configured", ephemeral=True
        )
    await interaction.response.send_message(
        overview,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions(users=False),
    )

tree.add_command(sponsor_group)



@tree.command(
    name=enums.Command.AUTOLOG, description=enums.Command.AUTOLOG.description()
)
@discord_command.choices(
    state=[
        discord_command.Choice(name=enums.AutologState.ON, value=enums.AutologState.ON),
        discord_command.Choice(
            name=enums.AutologState.OFF, value=enums.AutologState.OFF
        ),
    ]
)
async def command_autolog(
    interaction: discord.Interaction,
    channel: Optional[discord.TextChannel],
    state: Optional[discord_command.Choice[str]],
):
    global settings

    state = (
        enums.AutologState(state.value) if state is not None else enums.AutologState.ON
    )

    reply_message = bot_utils.autolog_command(channel, state)
    if reply_message is not None:
        await interaction.response.send_message(reply_message)
    if reply_message is None:
        await interaction.response.send_message(f"Nothing to do.")


giveaway_pool = []

giveaway_group = discord_command.Group(name="giveaway", description="Giveaway commands")


@giveaway_group.command(name="add", description="Add users from CSV (user ID, entries)")
@discord_command.describe(csv_data="CSV (user ID, entries) without headers")
async def command_giveaway_add(interaction: discord.Interaction, csv_data: str):
    global giveaway_pool
    giveaway_pool.clear()
    added = 0
    try:
        parts = [[x.strip() for x in p.split(",")] for p in csv_data.split(";")]
        new_pool = []
        for row in parts:
            if len(row) == 0:
                continue
            if len(row) != 2:
                raise ValueError(f"Invalid row: {str(row)}")
            user_id, count = row
            try:
                user_id = int(user_id.strip())
                count = int(count.strip())
                member = interaction.guild.get_member(user_id)
                if not member:
                    raise ValueError(
                        f"User with ID {user_id} is not a member of this server"
                    )
                new_pool.extend([user_id] * count)
                added += 1
            except ValueError as e:
                await interaction.response.send_message(f"Error: {e}")
                return
        giveaway_pool = new_pool
        await interaction.response.send_message(
            f"Added {added} users to the pool with a total of {len(giveaway_pool)} entries"
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Error: Failed to parse CSV: {str(e)}", ephemeral=True
        )


@giveaway_group.command(name="roll", description="Roll a random winner")
async def command_giveaway_roll(interaction: discord.Interaction):
    global giveaway_pool
    if not giveaway_pool:
        await interaction.response.send_message(
            "Add users to the pool first", ephemeral=True
        )
        return
    await interaction.response.send_message("Let's see who the winner is!")
    await asyncio.sleep(1)
    await interaction.channel.send("Where are my glasses?")
    await asyncio.sleep(2)
    await interaction.channel.send("Okay, I got them! Rolling the dice...")
    await asyncio.sleep(0.75)
    chosen_user = secrets.choice(giveaway_pool)
    await interaction.channel.send(
        f"Congratulations <@{chosen_user}>! You won the giveaway!"
    )


@giveaway_group.command(name="clear", description="Clear the giveaway pool")
async def command_giveaway_clear(interaction: discord.Interaction):
    global giveaway_pool
    giveaway_pool.clear()
    await interaction.response.send_message("Giveaway pool cleared")


tree.add_command(giveaway_group)

client.run(os.getenv("BOT_TOKEN"))
