"""Tank Backend - Entry point for the API server."""

import argparse
import uvicorn

from tank_backend.config.settings import create_example_env_file


def main():
    parser = argparse.ArgumentParser(description="Tank Backend API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--config", type=str, default=".env", help="Config file path")
    parser.add_argument("--create-config", action="store_true", help="Create example config file")

    args = parser.parse_args()

    if args.create_config:
        create_example_env_file()
        print("Example configuration file created at .env.example")
        print("Please copy it to .env and fill in your API keys.")
        return

    from tank_backend.api.server import app
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
