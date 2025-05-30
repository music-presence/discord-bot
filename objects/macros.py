from datetime import timezone
import discord


class Macro:
    """
    A representation of a column in the `macros` table.
    """

    def __init__(
        self,
        name: str,
        title: str,
        description: str,
        creator: int,
        date_created: float,
        date_edited: float = None,
        image_url: str = None,
        embed_color: str = None,
    ):
        self.name = name
        self.title = title
        self.description = description
        self.creator = creator
        self.date_created = date_created
        self.date_edited = date_created if date_edited is None else date_edited
        self.image_url = image_url
        self.embed_color = embed_color

    @classmethod
    def from_create_interaction(
        cls,
        name: str,
        title: str,
        description: str,
        ctx: discord.Interaction,
        color: str | None = None,
        image_url: str | None = None,
    ):
        created_time = ctx.created_at.replace(tzinfo=timezone.utc).timestamp()

        return cls(
            name,
            title,
            description,
            ctx.user.id,
            created_time,
            image_url=image_url,
            embed_color=color,
        )
