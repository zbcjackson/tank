from textual.widgets import Input

class InputFooter(Input):
    DEFAULT_CSS = """
    InputFooter {
        dock: bottom;
        margin: 0 1 1 1;
    }
    """
    
    def __init__(self):
        super().__init__(placeholder="Type your message here... (Type 'quit' to exit)", id="user_input")
