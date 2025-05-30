import sqlite3
import discord
from collections.abc import Callable
from discord import ui

from objects.macros import Macro
from objects.macro_embed import MacroEmbed
from utils.macros_database import add_macro, edit_macro


class ConfirmationView(ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, _: discord.Interaction, __: discord.ui.Button):
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, _: discord.Interaction, __: discord.ui.Button):
        self.value = False
        self.stop()


class MacroModal(ui.Modal):
    macro_title = ui.TextInput(label="Title", style=discord.TextStyle.short)
    macro_description = ui.TextInput(
        label="Contents", style=discord.TextStyle.paragraph
    )
    macro_image_url = ui.TextInput(
        label="Image URL (optional)", style=discord.TextStyle.short, required=False
    )
    macro_color = ui.TextInput(
        label="Embed Color (optional, hex code with #)",
        style=discord.TextStyle.short,
        required=False,
    )

    def __init__(
        self, modal_title: str, macros_db: sqlite3.Connection, macro: Macro = None
    ):
        super().__init__(title=modal_title)
        self.macros_db = macros_db
        self.macro = macro

    async def on_submit(
        self,
        interaction: discord.Interaction,
        db_callback: Callable[[sqlite3.Connection, Macro], int],
        prompt_msg: str,
        confirm_msg: str,
        cancel_msg: str,
    ):

        embed = MacroEmbed(self.macro).show_embed()
        buttons = ConfirmationView()

        if self.macro.image_url:
            embed.set_image(url=self.macro.image_url)

        await interaction.response.send_message(
            prompt_msg,
            embed=embed,
            view=buttons,
            ephemeral=True,
        )
        await buttons.wait()

        if buttons.value:
            db_callback(self.macros_db, self.macro)
            await interaction.edit_original_response(content=confirm_msg, view=None)
        else:
            await interaction.edit_original_response(
                content=cancel_msg, embed=None, view=None
            )


class MacroCreate(MacroModal):
    def __init__(self, macro_name: str, macros_db: sqlite3.Connection):
        self.macro_name = macro_name
        super().__init__(f"Creating macro: {macro_name}", macros_db)

    async def on_submit(self, interaction: discord.Interaction):
        self.macro = Macro.from_create_interaction(
            name=self.macro_name,
            title=self.macro_title.value,
            description=self.macro_description.value,
            ctx=interaction,
            color=self.macro_color.value,
            image_url=self.macro_image_url.value,
        )

        return await super().on_submit(
            interaction,
            db_callback=add_macro,
            prompt_msg=f"Is this okay for macro `{self.macro.name}`?",
            confirm_msg=f"Macro `{self.macro.name}` added.",
            cancel_msg="Macro creation cancelled.",
        )


class MacroEdit(MacroModal):
    def __init__(self, macro: Macro, macros_db: sqlite3.Connection):
        super().__init__(f"Editing macro: {macro.name}", macros_db, macro)

        self.macro_title.default = self.macro.title
        self.macro_description.default = self.macro.description
        self.macro_color.default = self.macro.embed_color
        self.macro_image_url.default = self.macro.image_url

    async def on_submit(self, interaction: discord.Interaction):
        self.macro.title = self.macro_title.value
        self.macro.description = self.macro_description.value
        self.macro.image_url = self.macro_image_url.value
        self.macro.embed_color = self.macro_color.value

        return await super().on_submit(
            interaction,
            db_callback=edit_macro,
            prompt_msg=f"Is this okay for macro `{self.macro.name}`?",
            confirm_msg=f"Macro `{self.macro.name}` edited.",
            cancel_msg="Macro edit cancelled.",
        )
