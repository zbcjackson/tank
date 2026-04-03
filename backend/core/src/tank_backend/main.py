"""Tank Backend - Entry point for the API server."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Tank Backend API Server")
    subparsers = parser.add_subparsers(dest="command")

    # Default: run the server (no subcommand)
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--config", type=str, default=".env", help="Config file path")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on file changes")

    # backup subcommand
    backup_parser = subparsers.add_parser("backup", help="Manage file backups")
    backup_sub = backup_parser.add_subparsers(dest="backup_action")

    list_parser = backup_sub.add_parser("list", help="List backups")
    list_parser.add_argument(
        "--days", type=int, default=30, help="Show backups from last N days (default: 30)",
    )

    restore_parser = backup_sub.add_parser("restore", help="Restore a backup")
    restore_parser.add_argument("path", help="Backup file path to restore")

    args = parser.parse_args()

    if args.command == "backup":
        _handle_backup(args)
    else:
        _run_server(args)


def _run_server(args: argparse.Namespace) -> None:
    import uvicorn

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


def _handle_backup(args: argparse.Namespace) -> None:
    if args.backup_action == "list":
        _backup_list(args.days)
    elif args.backup_action == "restore":
        _backup_restore(args.path)
    else:
        print("Usage: tank-backend backup {list,restore}")
        sys.exit(1)


def _backup_list(days: int) -> None:
    """List backup snapshots from ~/.tank/backups/."""
    import os
    from datetime import datetime, timedelta
    from pathlib import Path

    backup_dir = Path("~/.tank/backups").expanduser()
    if not backup_dir.exists():
        print("No backups found.")
        return

    cutoff = datetime.now() - timedelta(days=days)
    found = 0

    for entry in sorted(os.scandir(backup_dir), key=lambda e: e.name, reverse=True):
        if not entry.is_dir():
            continue
        try:
            dir_time = datetime.strptime(entry.name, "%Y-%m-%dT%H-%M-%S")
        except ValueError:
            continue
        if dir_time < cutoff:
            continue

        # List files in this snapshot
        snapshot_path = Path(entry.path)
        files = list(snapshot_path.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())
        if file_count == 0:
            continue

        found += 1
        print(f"\n{entry.name}  ({file_count} file{'s' if file_count != 1 else ''})")
        for f in sorted(files):
            if f.is_file():
                size = f.stat().st_size
                rel = f.relative_to(snapshot_path)
                print(f"  /{rel}  ({size:,} bytes)")

    if found == 0:
        print(f"No backups found in the last {days} days.")
    else:
        print(f"\n{found} snapshot{'s' if found != 1 else ''} found.")


def _backup_restore(backup_path: str) -> None:
    """Restore a file from a backup snapshot."""
    import shutil
    from pathlib import Path

    src = Path(backup_path).expanduser().resolve()
    if not src.exists():
        print(f"Backup file not found: {backup_path}")
        sys.exit(1)
    if not src.is_file():
        print(f"Not a file: {backup_path}")
        sys.exit(1)

    # Derive original path from backup structure:
    # ~/.tank/backups/2026-03-31T14-22-01/Users/alice/projects/app.py
    # → /Users/alice/projects/app.py
    backup_dir = Path("~/.tank/backups").expanduser().resolve()
    try:
        rel = src.relative_to(backup_dir)
    except ValueError:
        print(f"Path is not inside backup directory ({backup_dir}): {backup_path}")
        sys.exit(1)

    # First component is the timestamp directory
    parts = rel.parts
    if len(parts) < 2:
        print(f"Cannot determine original path from: {backup_path}")
        sys.exit(1)

    original = Path("/") / Path(*parts[1:])

    if original.exists():
        print(f"Target exists: {original}")
        confirm = input("Overwrite? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            sys.exit(0)

    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, original)
    print(f"Restored: {original}")


if __name__ == "__main__":
    main()
