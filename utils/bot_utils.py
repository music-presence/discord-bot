import asyncio
import json
import sqlite3
import re
import aiohttp
import pickledb
import discord
import dataclasses

import enums
import objects

from collections import defaultdict
from typing import Optional
from time import time

from enums.constants import (
    MIN_RETENTION_UPDATE_INTERVAL,
    MAX_USER_APP_ID_RETENTION,
    MUSIC_APP_ID,
    PODCAST_APP_ID,
    PLAYERS_JSON_URL,
    HELP_DOWNLOAD_URLS_FORMAT,
    HELP_MESSAGE_LINES,
)
from objects import LogRequestMatcher
from utils.github_cached import latest_github_release_version
from utils.macros_database import macros_list


def rreplace(s: str, old: str, new: str, occurrence: int = 1):
    li = s.rsplit(old, occurrence)
    return new.join(li)


# Find a better name maybe
class BotUtils:
    def __init__(
        self,
        client: discord.Client,
        macros_db: sqlite3.Connection,
        settings: pickledb.PickleDB,
        tree: discord.app_commands.CommandTree,
    ):
        self.macros_db = macros_db
        self.client = client
        self.settings = settings
        self.tree = tree
        self.macros_cache = []

        self.update_macros_cache()

    def get_role_listener(
        self, guild: discord.Guild, role: discord.Role
    ) -> discord.Role | None:
        role_id = str(role.id)
        guild_id = str(guild.id)
        if self.settings.dexists(enums.SettingsKeys.ROLES, guild_id):
            guild_roles = self.settings.dget(enums.SettingsKeys.ROLES, guild_id)
            if role_id in guild_roles:
                listener_role_id = guild_roles[role_id]
                listener_role = guild.get_role(listener_role_id)
                if listener_role is None:
                    # the role seems to have been deleted
                    del guild_roles[role_id]
                    self.settings.dadd(
                        enums.SettingsKeys.ROLES, (guild_id, guild_roles)
                    )

                return listener_role

        return None

    def get_roles_listeners_of_guild(self, guild: discord.Guild) -> list[discord.Role]:
        guild_id = str(guild.id)
        roles = []
        if self.settings.dexists(enums.SettingsKeys.ROLES, guild_id):
            guild_roles = self.settings.dget(enums.SettingsKeys.ROLES, guild_id)

            modified = False
            for role_id, listener_role_id in guild_roles.items():
                listener_role = guild.get_role(listener_role_id)
                if listener_role is None:
                    # the role seems to have been deleted
                    del guild_roles[role_id]
                    modified = True
                else:
                    roles.append(listener_role)

            if modified:
                self.settings.dadd(enums.SettingsKeys.ROLES, (guild_id, guild_roles))

        return roles

    async def give_role_listener(self, member: discord.Member):
        for role in reversed(member.roles):
            listener_role = self.get_role_listener(member.guild, role)
            if listener_role is not None:
                if listener_role not in member.roles:
                    await member.add_roles(listener_role)
                return

    async def clear_role_listeners_of_member(self, member: discord.Member):
        for listener_role in self.get_roles_listeners_of_guild(member.guild):
            if listener_role in member.roles:
                await member.remove_roles(listener_role)

    async def clear_role_listener_of_role(
        self, guild: discord.Guild, role: discord.Role
    ) -> discord.Role | None:
        listener_role = self.get_role_listener(guild, role)
        if listener_role is not None:
            for member in listener_role.members:
                await member.remove_roles(listener_role)

        return listener_role

    async def remove_all_listener_roles_from_all(self, guild: discord.Guild):
        for listener_role in self.get_roles_listeners_of_guild(guild):
            for member in guild.members:
                if listener_role in member.roles:
                    await member.remove_roles(listener_role)

    async def check_member(self, member: discord.Member):
        if member.status in (discord.Status.invisible, discord.Status.offline):
            return await self.clear_role_listeners_of_member(member)

        apps = self.settings.get(enums.SettingsKeys.APPS)
        user_apps = {}
        if self.settings.dexists(enums.SettingsKeys.USER_APPS, str(member.id)):
            user_apps = self.settings.dget(enums.SettingsKeys.USER_APPS, str(member.id))

        for activity in member.activities:
            if (
                not isinstance(activity, discord.Spotify)
                and isinstance(activity, discord.Activity)
                and (
                    str(activity.application_id) in apps
                    or str(activity.application_id) in user_apps
                )
            ):
                app_id_key = str(activity.application_id)
                if app_id_key in user_apps:
                    # Update the timestamp to the current time
                    # since this user app ID was used now.
                    info = objects.UserApp(**user_apps[app_id_key])
                    now = int(time())
                    if info.timestamp + MIN_RETENTION_UPDATE_INTERVAL < now:
                        # Make sure it's not updated too frequently though
                        info.timestamp = now
                        user_apps[app_id_key] = dataclasses.asdict(info)
                        self.settings.dadd(
                            enums.SettingsKeys.USER_APPS, (str(member.id), user_apps)
                        )
                return await self.give_role_listener(member)

        await self.clear_role_listeners_of_member(member)

    async def check_guild(self, guild: discord.Guild):
        if self.settings.dexists(enums.SettingsKeys.ROLES, str(guild.id)):
            for member in guild.members:
                await self.check_member(member)

    async def check_guilds(self):
        for guild in self.client.guilds:
            await self.check_guild(guild)

    async def setup_guild(self, guild: discord.Guild):
        self.tree.copy_global_to(guild=guild)
        commands = await self.tree.sync(guild=guild)
        print(
            f"Synced {len(commands)} commands: {', '.join([c.name for c in commands])}"
        )

    async def purge_user_app_ids(self):
        apps = self.settings.get(enums.SettingsKeys.APPS)
        user_apps = self.settings.get(enums.SettingsKeys.USER_APPS)
        sanitized = {}
        for user_id, value in user_apps.items():
            result = {}
            for app_id, info in value.items():
                # Remove app ids that are already known
                if str(app_id) in apps:
                    print(f"Deleted known user app ID {app_id} for user {user_id}")
                    continue

                # Remove app ids that are past their max age
                parsed_info = objects.UserApp(**info)
                print("parsed_info", parsed_info)
                if parsed_info.timestamp + MAX_USER_APP_ID_RETENTION < int(time()):
                    print(f"Deleted expired user app ID {app_id} for user {user_id}")
                    continue

                result[str(app_id)] = info

            if len(result) > 0:
                sanitized[user_id] = result

        self.settings.set(enums.SettingsKeys.USER_APPS, sanitized)

    async def update_apps(self):
        result = {str(MUSIC_APP_ID): True, str(PODCAST_APP_ID): True}

        # TODO clean this up
        async with aiohttp.ClientSession() as session:
            async with session.get(PLAYERS_JSON_URL) as response:
                if response.status != 200:
                    print("failed to download players from", PLAYERS_JSON_URL)
                    return

                players = json.loads(await response.read())
                for player in players["players"]:
                    if (
                        "extra" in player
                        and "discord_application_id" in player["extra"]
                    ):
                        app_id = player["extra"]["discord_application_id"]
                        result[str(app_id)] = True
                    else:
                        print("player", player, "does not have a discord app id")

        self.settings.set(enums.SettingsKeys.APPS, result)
        print(f"Updated application IDs ({len(result)} entries)")
        await self.purge_user_app_ids()

    async def update_apps_periodically(self):
        while True:
            print("Updating application IDs")
            await self.update_apps()
            await self.check_guilds()
            await asyncio.sleep(60 * 60 * 8)

    def get_role_overview(self, guild: discord.Guild) -> str | None:
        if not self.settings.dexists(enums.SettingsKeys.ROLES, str(guild.id)):
            return None

        inverse = defaultdict(list)
        guild_roles = self.settings.dget(enums.SettingsKeys.ROLES, str(guild.id))
        for for_role_id, listener_role_id in guild_roles.items():
            inverse[listener_role_id].append(for_role_id)

        lines = []
        for listener_role_id, for_role_ids in inverse.items():
            lines.append(
                f"- <@&{listener_role_id}> is assigned to {rreplace(', '.join([
                    f"<@&{role_id}>" for role_id in for_role_ids
                ]), ', ', ' and ')}"
            )

        return "\n".join(lines)

    def tester_coverage_compute(
        self, beta_tester_role: discord.Role, os_roles: list[discord.Role]
    ) -> dict[int, list[discord.Member]]:
        coverage: dict[int, list[discord.Member]] = {}
        for os_role in os_roles:
            coverage[os_role.id] = []

        for beta_tester in beta_tester_role.members:
            for os_role in os_roles:
                if os_role in beta_tester.roles:
                    coverage[os_role.id].append(beta_tester)

        return coverage

    def tester_coverage_make_embed(
        self,
        beta_tester_role: discord.Role,
        os_roles: list[discord.Role],
        coverage: dict[int, list[discord.Member]],
    ) -> discord.Embed:
        embed = discord.Embed(title="Music Presence users tests coverage")
        embed.add_field(
            name=f"{len(beta_tester_role.members)} beta tester{'s' if len(beta_tester_role.members) > 1 else ''}",
            value=f"> {', '.join([f"<@{m.id}>" for m in beta_tester_role.members])}\n\n",
        )
        for os_role in os_roles:
            value = "> "
            os_coverage_members = coverage.get(os_role.id)
            if len(os_coverage_members) == 0:
                value += ":warning:"
            else:
                value += f":white_check_mark: (covered by {len(os_coverage_members)} member{'s' if len(os_coverage_members) > 1 else ''})\n"
                value += f"> {', '.join([f"<@{m.id}>" for m in os_coverage_members])}"

            embed.add_field(name=f"{os_role.name}", value=value, inline=False)

        return embed

    def logs_response(self, platform: enums.Platform | None = None) -> str:
        lines = ["You can find the log file for Music Presence"]
        if platform is None:
            lines[0] += " here:"
            for plt in enums.Platform:
                filepath = plt.log_files_path()
                lines.append(f"- {plt.value}: `{filepath}`")
        else:
            lines[0] += f" on {platform.value} here:"
            lines.append(f"`{platform.log_files_path()}`")

        return "\n".join(lines)

    async def logs_response_to_interaction(
        self, interaction: discord.Interaction, platform: enums.Platform | None = None
    ):
        await interaction.response.send_message(self.logs_response(platform))

    async def get_download_urls(self) -> list[tuple[str, str]]:
        version = await latest_github_release_version()
        return [
            (name, url.format(version=version))
            for name, url in HELP_DOWNLOAD_URLS_FORMAT
        ]

    def get_help_message(self, topic: Optional[enums.HelpTopic]):
        if topic in HELP_MESSAGE_LINES:
            return "\n".join(HELP_MESSAGE_LINES[topic])
        return "No help message for this topic available"

    def update_macros_cache(self):
        macros = macros_list(self.macros_db)
        self.macros_cache = [macro.name for macro in macros] if macros else []

    def search_macros(self, query: str):
        return [
            macro_name
            for macro_name in self.macros_cache
            if query.lower() in str(macro_name).lower()
        ]
        
    def get_platform_names(self, guild: discord.Guild) -> list[str]:
        guild_id = str(guild.id)
        if not self.settings.dexists(
            enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id
        ):
            return []
        platforms = self.settings.dget(
            enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id
        )
        return list(platforms.keys())

    def search_platforms(self, guild: discord.Guild, query: str) -> list[str]:
        return [
            name
            for name in self.get_platform_names(guild)
            if query.lower() in name.lower()
        ]   
    def get_sponsor_status(self, member: discord.Member):
        guild_id = str(member.guild.id)

        if not self.settings.dexists(enums.SettingsKeys.SPONSOR_ROLES, guild_id):
            return None

        roles_cfg = self.settings.dget(
            enums.SettingsKeys.SPONSOR_ROLES, guild_id
        )

        status = None
        monthly_id = roles_cfg.get("monthly")
        one_time_id = roles_cfg.get("normal")

        if monthly_id:
            role = member.guild.get_role(int(monthly_id))
            if role and role in member.roles:
                status = "subscription"

        if status is None and one_time_id:
            role = member.guild.get_role(int(one_time_id))
            if role and role in member.roles:
                status = "one-time"

        if status is None:
            return None

        platform_entries = []

        if self.settings.dexists(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id):
            role_map = self.settings.dget(
                enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id
            )
            for role_id_str, name in role_map.items():
                role = member.guild.get_role(int(role_id_str))
                if role and role in member.roles:
                    emoji = None
                    if self.settings.dexists(
                        enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id
                    ):
                        platforms = self.settings.dget(
                            enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id
                        )
                        emoji = platforms.get(name)
                    platform_entries.append({
                        "name": name,
                        "emoji": emoji.get("emoji") if isinstance(emoji, dict) else emoji,
                        "url": emoji.get("url") if isinstance(emoji, dict) else None
                    })

        return {
            "type": status,
            "platforms": platform_entries
        }
    def get_platform_overview(self, guild: discord.Guild) -> str | None:
        guild_id = str(guild.id)

        if not self.settings.dexists(enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id):
            return None

        platforms = self.settings.dget(enums.SettingsKeys.SPONSOR_PLATFORMS, guild_id)
        role_map = (
            self.settings.dget(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id)
            if self.settings.dexists(enums.SettingsKeys.SPONSOR_PLATFORM_ROLES, guild_id)
            else {}
        )

        lines = []
        for name, data in platforms.items():
            # Handle legacy string entries
            if isinstance(data, str):
                emoji = data
                url = None
            else:
                emoji = data.get("emoji", "")
                url = data.get("url")

            role_ids = [
                int(rid)
                for rid, plat in role_map.items()
                if plat == name and guild.get_role(int(rid)) is not None
            ]
            role_mentions = ", ".join(f"<@&{rid}>" for rid in role_ids) if role_ids else ""

            line = f"- {emoji} `{name}`"
            if url:
                line += f" ([link]({url}))"
            if role_mentions:
                line += f" -> {role_mentions}"

            lines.append(line)

        return "\n".join(lines) if lines else None

    def get_sponsor_list(self, guild: discord.Guild) -> str | None:
        guild_id = str(guild.id)

        if not self.settings.dexists(enums.SettingsKeys.SPONSOR_ROLES, guild_id):
            return None

        roles_cfg = self.settings.dget(enums.SettingsKeys.SPONSOR_ROLES, guild_id)
        monthly_role = (
            guild.get_role(int(roles_cfg.get("monthly"))) if roles_cfg.get("monthly") else None
        )
        normal_role = (
            guild.get_role(int(roles_cfg.get("normal"))) if roles_cfg.get("normal") else None
        )

        lines = []
        if monthly_role is not None:
            members = [m.mention for m in monthly_role.members if not m.bot]
            value = ", ".join(members) if members else "None"
            lines.append(f"**Monthly** ({len(members)}): {value}")

        if normal_role is not None:
            members = [m.mention for m in normal_role.members if not m.bot]
            value = ", ".join(members) if members else "None"
            lines.append(f"**One Time** ({len(members)}): {value}")

        return "\n".join(lines) if lines else None
    
    async def autolog(self, message: discord.Message):
        is_channel_observed = self.settings.lexists(
            enums.SettingsKeys.AUTOLOG, f"{message.guild.id}:{message.channel.id}"
        )
        if is_channel_observed and LogRequestMatcher().test(message.content):
            await message.reply(self.logs_response())

    def autolog_command(
        self, channel: discord.TextChannel | None, state: enums.AutologState
    ) -> str | None:
        if channel is not None:
            channel_value = f"{channel.guild.id}:{channel.id}"
            is_channel_observed = self.settings.lexists(
                enums.SettingsKeys.AUTOLOG, channel_value
            )

            if state is enums.AutologState.ON:
                if not is_channel_observed:
                    self.settings.ladd(enums.SettingsKeys.AUTOLOG, channel_value)
                    return f"The channel <#{channel.id}> is now observed."
                if is_channel_observed:
                    return f"The channel <#{channel.id}> is already observed. Nothing to do."

            if state is enums.AutologState.OFF:
                if is_channel_observed:
                    self.settings.lremvalue(enums.SettingsKeys.AUTOLOG, channel_value)
                    return f"The channel <#{channel.id}> is no longer observed."
                if not is_channel_observed:
                    return f"The channel <#{channel.id}> is currently unobserved. Nothing to do."

        if channel is None and state is enums.AutologState.OFF:
            if self.settings.exists(enums.SettingsKeys.AUTOLOG):
                self.settings.lremlist(enums.SettingsKeys.AUTOLOG)
                self.settings.lcreate(enums.SettingsKeys.AUTOLOG)
            return f"All channels were removed from observation."
