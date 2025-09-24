import asyncio
import argparse
from pathlib import Path
from src.voice_assistant.assistant import VoiceAssistant
from src.voice_assistant.config.settings import create_example_env_file

async def main():
    parser = argparse.ArgumentParser(description="Bilingual Voice Assistant")
    parser.add_argument("--config", type=str, help="Path to config file", default=".env")
    parser.add_argument("--check", action="store_true", help="Check system status")
    parser.add_argument("--create-config", action="store_true", help="Create example config file")

    args = parser.parse_args()

    if args.create_config:
        create_example_env_file()
        print("Example configuration file created at .env.example")
        print("Please copy it to .env and fill in your API keys.")
        return

    config_path = Path(args.config) if args.config else None

    try:
        assistant = VoiceAssistant(config_path)

        if args.check:
            print("Checking system status...")
            status = await assistant.check_system_status()
            for component, state in status.items():
                print(f"  {component}: {state}")
            return

        await assistant.conversation_loop()

    except FileNotFoundError:
        print("Configuration file not found!")
        print("Run with --create-config to create an example configuration file.")
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please check your configuration file and API keys.")
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
