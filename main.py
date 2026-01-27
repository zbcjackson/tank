import asyncio
import argparse
from pathlib import Path
from src.voice_assistant.core.cli import CLI
from src.voice_assistant.config.settings import create_example_env_file

# Note: The original async main loop is replaced by the threaded CLI for the refactor.
# We are keeping the file name main.py as requested but switching to the threaded implementation.

def main():
    parser = argparse.ArgumentParser(description="Bilingual Voice Assistant (Threaded Architecture)")
    parser.add_argument("--config", type=str, help="Path to config file", default=".env")
    parser.add_argument("--create-config", action="store_true", help="Create example config file")

    args = parser.parse_args()

    if args.create_config:
        create_example_env_file()
        print("Example configuration file created at .env.example")
        print("Please copy it to .env and fill in your API keys.")
        return

    # Initialize and run the threaded CLI
    app = CLI()
    app.start()

if __name__ == "__main__":
    main()