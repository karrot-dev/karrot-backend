from karrot.conversations import emoji_db


def normalize_emoji_name(name: str) -> str:
    """Return a normalized name of emoji (important when the same emoji has multiple names)"""

    if name in emoji_db.emoji:
        return name

    if name in emoji_db.aliases:
        return emoji_db.aliases[name]

    # when not found, raise error
    raise Exception("not found")
