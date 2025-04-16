import pickledb


def load_database(version: int = 0) -> pickledb.PickleDB:
    settings = pickledb.load(f"settings.{version}.db", True)
    for key in ["apps", "user_apps", "roles"]:
        if not settings.exists(key):
            settings.dcreate(key)

    return settings
