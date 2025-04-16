from enum import StrEnum


class Platform(StrEnum):
    WIN = "Windows"
    MAC = "Mac"
    LIN = "Linux"

    def log_files_path(self) -> str:
        return {
            self.WIN: "%APPDATA%\\Music Presence\\presence.log",
            self.LIN: "~/.local/share/Music Presence/presence.log",
            self.MAC: "~/Library/Application Support/Music Presence/presence.log",
        }[self]
