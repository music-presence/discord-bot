import enums

MUSIC_APP_ID = 1205619376275980288
PODCAST_APP_ID = 1292142821482172506
PLAYERS_JSON_URL = "https://live.musicpresence.app/v3/players.min.json"
MAX_USER_APP_ID_RETENTION = 60 * 60 * 24 * 30  # 30 days (in seconds)
MIN_RETENTION_UPDATE_INTERVAL = 60 * 60 * 24  # 24 hours (in seconds)

ROLE_BETA_TESTER = 1349699182968967219
ROLES_OS = [1295480990722035752, 1295480950242676737, 1295480841987821628]
ROLES_USE_MACROS = ["Moderator"]

HELP_URL_INSTALL = "https://github.com/ungive/discord-music-presence/blob/master/documentation/installation-instructions.md"
HELP_URL_TROUBLESHOOTING = "https://github.com/ungive/discord-music-presence/blob/master/documentation/troubleshooting.md"
HELP_MESSAGE_LINES = {
    None: [
        f"Choose the topic you need help with:",
        f"- **{enums.HelpTopic.INSTALL.value}**: For detailed installation instructions read the steps outlined [**here**](<{HELP_URL_INSTALL}>). "
        f"If you can't find the download links for Music Presence, use the `/help topic:{enums.HelpTopic.INSTALL.name}` command",
        f"- **{enums.HelpTopic.PLAYER_DETECTION.value}**: For troubleshooting undetected media players find help [**here**](<{HELP_URL_TROUBLESHOOTING}>)",
        f"- **{enums.HelpTopic.APP_LOGS.value}**: For paths to log files use the `/{enums.Command.LOGS}` command",
    ],
    enums.HelpTopic.INSTALL: [
        f"- To download the app, click any of the buttons below",
        f"- Read the installation instructions [**here**](<{HELP_URL_INSTALL}>) "
        f"if you need help with installing Music Presence",
    ],
    enums.HelpTopic.PLAYER_DETECTION: [
        f"- For troubleshooting undetected media players find help [**here**](<{HELP_URL_TROUBLESHOOTING}>)",
        f"- Note that your media player might need a plugin to work with Music Presence. "
        f"You'll find more information at the provided help page",
    ],
}
HELP_DOWNLOAD_URLS_FORMAT = [
    (
        "Windows",
        "https://github.com/ungive/discord-music-presence/releases/download/v{version}/musicpresence-{version}-windows-x64-installer.exe",
    ),
    (
        "Mac Apple Silicon",
        "https://github.com/ungive/discord-music-presence/releases/download/v{version}/musicpresence-{version}-mac-arm64.dmg",
    ),
    (
        "Mac Intel",
        "https://github.com/ungive/discord-music-presence/releases/download/v{version}/musicpresence-{version}-mac-x86_64.dmg",
    ),
    (
        "All downloads",
        "https://github.com/ungive/discord-music-presence/releases/latest",
    ),
]
HELP_TROUBLESHOOTING_URLS = [("Troubleshooting", HELP_URL_TROUBLESHOOTING)]
