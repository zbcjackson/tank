"""Tank CLI - Entry point for the TUI client."""

import argparse

from tank_cli.config.settings import create_example_env_file


def main():
    parser = argparse.ArgumentParser(description="Tank CLI/TUI Client")
    parser.add_argument("--server", default="localhost:8000", help="Backend server URL")
    parser.add_argument("--create-config", action="store_true", help="Create example config file")

    args = parser.parse_args()

    if args.create_config:
        create_example_env_file()
        print("Example configuration file created at .env.example")
        print("Please copy it to .env and fill in your API keys.")
        return

    from tank_cli.tui.app import TankApp
    app = TankApp(server_url=args.server)
    app.run()


if __name__ == "__main__":
    main()
