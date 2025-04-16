import json
import re
import traceback
import aiohttp

from memoize.configuration import DefaultInMemoryCacheConfiguration
from memoize.wrapper import memoize
from datetime import timedelta

LATEST_RELEASE_URL = (
    "https://api.github.com/repos/ungive/discord-music-presence/releases?per_page=1"
)


@memoize(
    configuration=DefaultInMemoryCacheConfiguration(
        update_after=timedelta(minutes=15), expire_after=timedelta(minutes=30)
    )
)
async def latest_github_release_version() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(LATEST_RELEASE_URL) as response:
                if response.status != 200:
                    raise RuntimeError(
                        "Failed to get latest version from the GitHub API"
                    )
                data = json.loads(await response.read())
                if len(data) < 0:
                    raise RuntimeError("The GitHub API returned an empty result")
                latest_release = data[0]
                tag: str = latest_release["tag_name"]
                if not re.search(r"^v\d+\.\d+\.\d+$", tag):
                    raise RuntimeError(f"Bad version tag format: {tag}")
                return tag[1:]
    except Exception as e:
        print(f"GitHub API request failed: {e}")
        traceback.print_exc()

    return ""
