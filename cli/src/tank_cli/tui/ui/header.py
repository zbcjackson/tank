from textual.widgets import Header

class TankHeader(Header):
    DEFAULT_CSS = """
    TankHeader {
        dock: top;
        height: 1;
        content-align: center middle;
    }
    """
    def __init__(self):
        super().__init__(show_clock=True)
