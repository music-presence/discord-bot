from datetime import datetime, timezone
import sqlite3

from objects.macros import Macro


def add_macro(conn: sqlite3.Connection, macro: Macro) -> int:
    cur = conn.cursor()

    res = cur.execute(
        "INSERT INTO macros VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        (
            macro.name,
            macro.title,
            macro.description,
            macro.creator,
            macro.date_created,
            macro.date_edited,
            macro.image_url,
            macro.embed_color,
        ),
    )

    conn.commit()
    return res.rowcount


def edit_macro(conn: sqlite3.Connection, macro: Macro) -> int:
    cur = conn.cursor()
    macro.date_edited = datetime.now(tz=timezone.utc).timestamp()

    res = cur.execute(
        "UPDATE macros SET title=?, description=?, image_url=?, embed_color=?, date_edited=? WHERE name=?",
        (
            macro.title,
            macro.description,
            macro.image_url,
            macro.embed_color,
            macro.date_edited,
            macro.name,
        ),
    )

    conn.commit()
    return res.rowcount


def delete_macro(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.cursor()

    res = cur.execute("DELETE FROM macros WHERE name=?", (name,))

    conn.commit()
    return res.rowcount


def get_macro(conn: sqlite3.Connection, name: str) -> Macro | None:
    cur = conn.cursor()

    res = cur.execute("SELECT * FROM macros WHERE name=?", (name,))

    macro_tuple = res.fetchone()
    return Macro(*macro_tuple) if macro_tuple is not None else None


def macro_names(conn: sqlite3.Connection) -> tuple | None:
    cur = conn.cursor()

    res = cur.execute("SELECT name FROM macros ORDER BY date_edited DESC LIMIT 25")
    return res.fetchall()


def macros_list(conn: sqlite3.Connection) -> tuple | None:
    cur = conn.cursor()

    res = cur.execute("SELECT * FROM macros")

    macros = res.fetchall()
    return (
        [Macro(*macro_tuple) for macro_tuple in macros] if macros is not None else None
    )


def macro_search(conn: sqlite3.Connection, name: str) -> tuple | None:
    cur = conn.cursor()

    res = cur.execute(
        "SELECT name FROM macros WHERE name LIKE ? ORDER BY date_edited DESC LIMIT 25",
        (f"%{name}%",),
    )
    return res.fetchall()
