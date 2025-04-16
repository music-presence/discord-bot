from discord import ui


class LinkButtons(ui.View):
    def __init__(self, labelled_urls: list[tuple[str, str]]):
        super().__init__()
        for name, url in labelled_urls:
            self.add_item(ui.Button(label=name, url=url))
