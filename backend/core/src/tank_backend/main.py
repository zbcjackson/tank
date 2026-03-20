"""Tank Backend - Entry point for the API server."""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Tank Backend API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--config", type=str, default=".env", help="Config file path")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on file changes")

    args = parser.parse_args()

    if args.reload:
        uvicorn.run(
            "tank_backend.api.server:app",
            host=args.host,
            port=args.port,
            reload=True,
            reload_dirs=["."],
            reload_includes=["*.py", "config.yaml", ".env"],
        )
    else:
        from tank_backend.api.server import app

        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
