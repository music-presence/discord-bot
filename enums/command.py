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
    AUTOLOG = "autolog"
    DATEROLE = "daterole"
    INFO = "info"
    SPONSOR = "sponsor"
    SPONSOR_PLATFORM = "platform"
    SPONSOR_PLATFORM_ADD = "add"
    SPONSOR_PLATFORM_EDIT = "edit"
    SPONSOR_PLATFORM_DELETE = "delete"
    SPONSOR_PLATFORM_LIST = "list"
    SPONSOR_SUBROLES = "subroles"
    SPONSOR_INFO = "info"
    SPONSOR_LIST = "list"

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
            self.MACRO: "Shows a macro, and optionally adds a message.",
            self.MACROS: "Create, edit, and delete macros to be reused in troubleshooting.",
            self.MACROS_CREATE: "Creates a new macro.",
            self.MACROS_EDIT: "Edits an existing macro.",
            self.MACROS_LIST: "Lists all created macros.",
            self.MACROS_DELETE: "Deletes a macro.",
            self.AUTOLOG: "Automaticaly reply logs locations to a user asking for logs when his message match a regex.",
            self.DATEROLE: "Assign a role to all members who joined after a specific date.",
            self.INFO: "Display join date and sponsorship info for a member.",
            self.SPONSOR: "Manage sponsorship settings.",
            self.SPONSOR_PLATFORM: "Manage sponsorship platforms.",
            self.SPONSOR_PLATFORM_ADD: "Add a sponsorship platform and map its role.",
            self.SPONSOR_PLATFORM_EDIT: "Edit a sponsorship platform mapping.",
            self.SPONSOR_PLATFORM_DELETE: "Delete a sponsorship platform.",
            self.SPONSOR_PLATFORM_LIST: "List all sponsorship platforms.",
            self.SPONSOR_SUBROLES: "Configure roles for sponsors.",
            self.SPONSOR_INFO: "Show the sponsorship information for a member.",
            self.SPONSOR_LIST: "List all sponsors.",
        }[self]
