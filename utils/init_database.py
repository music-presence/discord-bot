import pickledb
import sqlite3


def load_settings_database(version: int = 0) -> pickledb.PickleDB:
    settings = pickledb.load(f"settings.{version}.db", True)
    for key in ["apps", "user_apps", "roles"]:
        if not settings.exists(key):
            settings.dcreate(key)

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
