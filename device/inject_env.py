"""Inject environment variables as build flags for device configuration.

Reads from environment variables, with fallback to .env file in project root.
"""
import os
from pathlib import Path

Import("env")

# Load .env file if present (does not override existing env vars)
env_file = Path(env.subst("$PROJECT_DIR")) / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        if key and _ and key not in os.environ:
            os.environ[key] = value

# Map: ENV_VAR -> (C macro name, is_string)
CONFIG_VARS = {
    "TANK_WIFI_SSID": ("CONFIG_WIFI_SSID", True),
    "TANK_WIFI_PASSWORD": ("CONFIG_WIFI_PASSWORD", True),
    "TANK_BACKEND_HOST": ("CONFIG_BACKEND_HOST", True),
    "TANK_BACKEND_PORT": ("CONFIG_BACKEND_PORT", False),
}

for env_var, (macro, is_string) in CONFIG_VARS.items():
    value = os.environ.get(env_var)
    if value:
        if is_string:
            env.Append(CPPDEFINES=[(macro, env.StringifyMacro(value))])
        else:
            env.Append(CPPDEFINES=[(macro, value)])
