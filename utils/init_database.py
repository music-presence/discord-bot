import pickledb
import sqlite3
import enums


def load_settings_database(version: int = 0) -> pickledb.PickleDB:
    settings = pickledb.load(f"settings.{version}.db", True)

    for key in [
        enums.SettingsKeys.ROLES,
        enums.SettingsKeys.APPS,
        enums.SettingsKeys.USER_APPS,
        enums.SettingsKeys.SPONSOR_PLATFORMS,
        enums.SettingsKeys.SPONSOR_ROLES,
        enums.SettingsKeys.SPONSOR_PLATFORM_ROLES,
    ]:
        if not settings.exists(key):
            settings.dcreate(key)

    if not settings.exists(enums.SettingsKeys.AUTOLOG):
        settings.lcreate(enums.SettingsKeys.AUTOLOG)

    return settings


def load_macros_database(db_file: str):
    conn = sqlite3.connect(db_file)

    cur = conn.cursor()

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS macros(
        name TEXT PRIMARY KEY NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        creator INTEGER NOT NULL,
        date_created REAL NOT NULL,
        date_edited REAL NOT NULL,
        image_url TEXT,
        embed_color TEXT
    )
    """
    )

    conn.commit()

    return conn
