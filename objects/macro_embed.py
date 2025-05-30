import discord

from objects.macros import Macro


class MacroEmbed:
    def __init__(self, macro: Macro):
        self.color = discord.Color.from_str(
            macro.embed_color if macro.embed_color else "#34353B"
        )
        self.macro = macro

    # This is a function because you cannot add images to the end of an embed regularly
    def show_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.macro.title, description=self.macro.description, color=self.color
        )

        if self.macro.image_url:
            embed.set_image(url=self.macro.image_url)

        return embed
