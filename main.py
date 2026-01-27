import argparse
from src.voice_assistant.core.tui import TankApp
from src.voice_assistant.config.settings import create_example_env_file

def main():
    parser = argparse.ArgumentParser(description="Bilingual Voice Assistant (TUI)")
    parser.add_argument("--config", type=str, help="Path to config file", default=".env")
    parser.add_argument("--create-config", action="store_true", help="Create example config file")

    args = parser.parse_args()

    if args.create_config:
        create_example_env_file()
        print("Example configuration file created at .env.example")
        print("Please copy it to .env and fill in your API keys.")
        return

    # Initialize and run the Textual App
    app = TankApp()
    app.run()

if __name__ == "__main__":
    main()
