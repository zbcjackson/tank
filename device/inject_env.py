"""Inject environment variables as build flags for device configuration."""
import os

Import("env")

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
