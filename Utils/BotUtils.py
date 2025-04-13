import asyncio
import json
from collections import defaultdict
from typing import Optional

import aiohttp
import pickledb
import discord
import dataclasses

from discord import Guild, Role, Client, Member, Interaction
from time import time

from Class.UserApp import UserApp
from Enum.PlatformEnum import PlatformEnum
from Enum.Constants import *
from Utils.Memoize import latest_github_release_version


def rreplace(s: str, old: str, new: str, occurrence: int = 1):
    li = s.rsplit(old, occurrence)
    return new.join(li)

# Find a better name maybe
class BotUtils:
    def __init__(self, client: Client, database: pickledb.PickleDB, tree: discord.app_commands.CommandTree):
        self.client = client
        self.database = database
        self.tree = tree

    def get_role_listener(self, guild: Guild, role: Role) -> Role | None:
        role_id = str(role.id)
        guild_id = str(guild.id)
        if self.database.dexists("roles", guild_id):
            guild_roles = self.database.dget("roles", guild_id)
            if role_id in guild_roles:
                listener_role_id = guild_roles[role_id]
                listener_role = guild.get_role(listener_role_id)
                if listener_role is None:
                    # the role seems to have been deleted
                    del guild_roles[role_id]
                    self.database.dadd("roles", (guild_id, guild_roles))

                return listener_role

        return None

    def get_roles_listeners(self, guild: Guild) -> list[Role]:
        guild_id = str(guild.id)
        roles = []
        if self.database.dexists("roles", guild_id):
            guild_roles = self.database.dget("roles", guild_id)

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
                self.database.dadd("roles", (guild_id, guild_roles))

        return roles

    async def give_listener_role(self, member: Member):
        for role in reversed(member.roles):
            listener_role = self.get_role_listener(member.guild, role)
            if listener_role is not None:
                if listener_role not in member.roles:
                    await member.add_roles(listener_role)
                return

    async def clear_member_roles_listeners(self, member: Member):
        for listener_role in self.get_roles_listeners(member.guild):
            if listener_role in member.roles:
                await member.remove_roles(listener_role)

    async def remove_listener_role_from_all(self, guild: Guild, for_role: Role) -> Role | None:
        listener_role = self.get_role_listener(guild, for_role)
        if listener_role is not None:
            for member in guild.members:
                if for_role in member.roles and listener_role in member.roles:
                    await member.remove_roles(listener_role)

        return listener_role

    async def remove_all_listener_roles_from_all(self, guild: Guild):
        for listener_role in self.get_roles_listeners(guild):
            for member in guild.members:
                if listener_role in member.roles:
                    await member.remove_roles(listener_role)

    async def check_member(self, member: Member):
        if member.status in (discord.Status.invisible, discord.Status.offline):
            return await self.clear_member_roles_listeners(member)

        apps = self.database.get("apps")
        user_apps = {}
        if self.database.dexists("user_apps", str(member.id)):
            user_apps = self.database.dget("user_apps", str(member.id))

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
                    info = UserApp(**user_apps[app_id_key])
                    now = int(time())
                    if info.timestamp + MIN_RETENTION_UPDATE_INTERVAL < now:
                        # Make sure it's not updated too frequently though
                        info.timestamp = now
                        user_apps[app_id_key] = dataclasses.asdict(info)
                        self.database.dadd("user_apps", (str(member.id), user_apps))
                return await self.give_listener_role(member)

        await self.clear_member_roles_listeners(member)

    async def check_guild(self, guild: Guild):
        if self.database.dexists("roles", str(guild.id)):
            for member in guild.members:
                await self.check_member(member)

    async def check_guilds(self):
        for guild in self.client.guilds:
            await self.check_guild(guild)

    async def setup_guild(self, guild: Guild):
        self.tree.copy_global_to(guild=guild)
        commands = await self.tree.sync(guild=guild)
        print(f"Synced {len(commands)} commands: {', '.join([c.name for c in commands])}")

    async def purge_user_app_ids(self):
        apps = self.database.get("apps")
        user_apps = self.database.get("user_apps")
        sanitized = {}
        for user_id, value in user_apps.items():
            result = {}
            for app_id, info in value.items():
                # Remove app ids that are already known
                if str(app_id) in apps:
                    print(f"Deleted known user app ID {app_id} for user {user_id}")
                    continue

                # Remove app ids that are past their max age
                parsed_info = UserApp(**info)
                print("parsed_info", parsed_info)
                if parsed_info.timestamp + MAX_USER_APP_ID_RETENTION < int(time()):
                    print(f"Deleted expired user app ID {app_id} for user {user_id}")
                    continue

                result[str(app_id)] = info

            if len(result) > 0:
                sanitized[user_id] = result

        self.database.set("user_apps", sanitized)

    async def update_apps(self):
        result = {
            str(MUSIC_APP_ID): True,
            str(PODCAST_APP_ID): True
        }

        # TODO clean this up
        async with aiohttp.ClientSession() as session:
            async with session.get(PLAYERS_JSON_URL) as response:
                if response.status != 200:
                    print("failed to download players from", PLAYERS_JSON_URL)
                    return

                players = json.loads(await response.read())
                for player in players["players"]:
                    if "extra" in player and "discord_application_id" in player["extra"]:
                        app_id = player["extra"]["discord_application_id"]
                        result[str(app_id)] = True
                    else:
                        print("player", player, "does not have a discord app id")

        self.database.set("apps", result)
        print(f"Updated application IDs ({len(result)} entries)")
        await self.purge_user_app_ids()

    async def update_apps_periodically(self):
        while True:
            print("Updating application IDs")
            await self.update_apps()
            await self.check_guilds()
            await asyncio.sleep(60 * 60 * 8)

    def get_role_overview(self, guild: Guild) -> str | None:
        if not self.database.dexists("roles", str(guild.id)):
            return None

        inverse = defaultdict(list)
        guild_roles = self.database.dget("roles", str(guild.id))
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

    async def logs_response(self, interaction: Interaction, platform: PlatformEnum | None = None):
        lines = ["You can find the log file for Music Presence"]
        if platform is None:
            lines[0] += " here:"
            for plt in PlatformEnum:
                filepath = plt.log_files_path()
                lines.append(f"- {plt.value}: `{filepath}`")
        else:
            lines[0] += f" on {platform.value} here:"
            lines.append(f"`{platform.log_files_path()}`")

        await interaction.response.send_message("\n".join(lines))

    async def get_download_urls(self) -> list[tuple[str, str]]:
        version = await latest_github_release_version()
        return [
            (name, url.format(version=version)) for name, url in HELP_DOWNLOAD_URLS_FORMAT
        ]

    def get_help_message(self, topic: Optional[HelpTopicEnum]):
        if topic in HELP_MESSAGE_LINES:
            return "\n".join(HELP_MESSAGE_LINES[topic])
        return "No help message for this topic available"
