from enum import StrEnum


class Command(StrEnum):
    ROLE = "role"
    ROLES = "roles"
    JOINED = "joined"
    LISTENING = "listening"
    STOP = "stop"
    LOGS = "logs"
    HELP = "help"
    TESTER_COVERAGE = "testers-coverage"
    MACRO = "macro"
    MACROS = "macros"
    MACROS_CREATE = "create"
    MACROS_EDIT = "edit"
    MACROS_LIST = "list"
    MACROS_DELETE = "delete"

    def description(self) -> str:
        return {
            self.ROLE: "Set or unset the role to give to active Music Presence listeners that have the specified roles",
            self.ROLES: "List all listener roles and their respective parent roles",
            self.JOINED: "Check the join time of yourself or another user with some extras",
            self.LISTENING: "Register your currently active listening status for the listener role",
            self.STOP: "Stop the bot and remove the listener role from all members in all servers",
            self.LOGS: "Tells you where the Music Presence logs are located",
            self.HELP: "Use this command if you need help with Music Presence",
            self.TESTER_COVERAGE: "Report the OS coverage among beta testers.",
            self.MACRO: "Shows a macro, and optionally mentions someone. Moderator only.",
            self.MACROS: "Create, edit, and delete macros to be reused in troubleshooting. Moderator only.",
            self.MACROS_CREATE: "Creates a new macro. Moderator only.",
            self.MACROS_EDIT: "Edits an existing macro. Moderator only.",
            self.MACROS_LIST: "Lists all created macros. Moderator only.",
            self.MACROS_DELETE: "Deletes a macro. Moderator only.",
        }[self]
