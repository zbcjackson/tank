import json
import logging
from datetime import datetime
from typing import Any

import requests

from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

logger = logging.getLogger("WeatherTool")

_DAILY_FIELDS = (
    "temperature_2m_max,temperature_2m_min,"
    "weathercode,precipitation_sum,windspeed_10m_max"
)

_CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,weathercode,windspeed_10m"
)

# WMO Weather interpretation codes
_WMO_CONDITIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="get_weather",
            description=(
                "Get weather information for a specific location and date. "
                "Can retrieve current weather, historical weather, "
                "or forecast up to 16 days ahead."
            ),
            parameters=[
                ToolParameter(
                    name="location",
                    type="string",
                    description=(
                        "The location to get weather for. "
                        "MUST use English name "
                        "(e.g., 'New York', 'Beijing', 'Tokyo', 'London'). "
                        "Always convert non-English location names to English "
                        "before calling this tool."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="date",
                    type="string",
                    description=(
                        "Optional date in YYYY-MM-DD format. "
                        "If not provided, returns current weather. "
                        "Can be a past date (historical), today (current), "
                        "or future date (forecast, up to 16 days)."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(
        self, location: str, date: str = None
    ) -> ToolResult:
        logger.info(f"Getting weather for: {location}, date: {date}")

        try:
            geocode_result = self._geocode_location(location)
            if "error" in geocode_result:
                return ToolResult(
                    content=json.dumps(
                        {"location": location, "error": geocode_result["error"]},
                        ensure_ascii=False,
                    ),
                    display=geocode_result.get("message", str(geocode_result["error"])),
                    error=True,
                )

            latitude = geocode_result["latitude"]
            longitude = geocode_result["longitude"]
            resolved_location = geocode_result["name"]

            weather_result = self._get_weather_data(
                latitude, longitude, date
            )
            if "error" in weather_result:
                return ToolResult(
                    content=json.dumps(
                        {"location": location, "error": weather_result["error"]},
                        ensure_ascii=False,
                    ),
                    display=weather_result.get("message", str(weather_result["error"])),
                    error=True,
                )

            weather_data = {
                "location": resolved_location,
                "coordinates": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "date": weather_result["date"],
                "temperature": weather_result["temperature"],
                "temperature_max": weather_result.get("temperature_max"),
                "temperature_min": weather_result.get("temperature_min"),
                "condition": weather_result["condition"],
                "humidity": weather_result.get("humidity"),
                "wind_speed": weather_result.get("wind_speed"),
                "precipitation": weather_result.get("precipitation"),
            }

            return ToolResult(
                content=json.dumps(weather_data, ensure_ascii=False),
                display=self._format_message(resolved_location, weather_result),
            )

        except Exception as e:
            logger.error(f"Error getting weather for '{location}': {e}")
            return ToolResult(
                content=json.dumps(
                    {"location": location, "error": str(e)},
                    ensure_ascii=False,
                ),
                display=(
                    f"Sorry, I couldn't retrieve weather information "
                    f"for '{location}'. Please try again."
                ),
                error=True,
            )

    def _geocode_location(self, location: str) -> dict[str, Any]:
        """Geocode location using Open-Meteo Geocoding API."""
        try:
            url = "https://geocoding-api.open-meteo.com/v1/search"
            params = {
                "name": location,
                "count": 1,
                "language": "en",
                "format": "json",
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if "results" not in data or len(data["results"]) == 0:
                return {
                    "error": "location_not_found",
                    "message": (
                        f"Could not find location '{location}'. "
                        "Please check the spelling or try a "
                        "different location."
                    ),
                }

            result = data["results"][0]
            return {
                "name": result["name"],
                "latitude": result["latitude"],
                "longitude": result["longitude"],
                "country": result.get("country", ""),
                "admin1": result.get("admin1", ""),
            }

        except Exception as e:
            logger.error(f"Geocoding error for '{location}': {e}")
            return {
                "error": "geocoding_failed",
                "message": (
                    f"Failed to geocode location '{location}': {e}"
                ),
            }

    def _get_weather_data(
        self, latitude: float, longitude: float, date: str = None
    ) -> dict[str, Any]:
        """Get weather data using Open-Meteo API."""
        try:
            today = datetime.now().date()
            target_date = (
                datetime.strptime(date, "%Y-%m-%d").date()
                if date
                else today
            )

            if target_date < today:
                url = "https://archive-api.open-meteo.com/v1/archive"
                params = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_date": target_date.isoformat(),
                    "end_date": target_date.isoformat(),
                    "daily": _DAILY_FIELDS,
                    "timezone": "auto",
                }
            else:
                url = "https://api.open-meteo.com/v1/forecast"
                params = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": _CURRENT_FIELDS,
                    "daily": _DAILY_FIELDS,
                    "timezone": "auto",
                    "forecast_days": 16,
                }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if target_date == today and "current" in data:
                current = data["current"]
                return {
                    "date": today.isoformat(),
                    "temperature": f"{current['temperature_2m']}°C",
                    "condition": self._weather_code_to_condition(
                        current["weathercode"]
                    ),
                    "humidity": (
                        f"{current.get('relative_humidity_2m', 'N/A')}%"
                    ),
                    "wind_speed": (
                        f"{current.get('windspeed_10m', 'N/A')} km/h"
                    ),
                }
            else:
                daily = data["daily"]
                idx = daily["time"].index(target_date.isoformat())
                t_max = daily["temperature_2m_max"][idx]
                t_min = daily["temperature_2m_min"][idx]

                return {
                    "date": target_date.isoformat(),
                    "temperature_max": f"{t_max}°C",
                    "temperature_min": f"{t_min}°C",
                    "temperature": f"{(t_max + t_min) / 2:.1f}°C",
                    "condition": self._weather_code_to_condition(
                        daily["weathercode"][idx]
                    ),
                    "precipitation": (
                        f"{daily['precipitation_sum'][idx]} mm"
                    ),
                    "wind_speed": (
                        f"{daily['windspeed_10m_max'][idx]} km/h"
                    ),
                }

        except ValueError as e:
            logger.error(f"Date parsing error: {e}")
            return {
                "error": "invalid_date",
                "message": (
                    "Invalid date format. "
                    "Please use YYYY-MM-DD format (e.g., '2026-03-12')."
                ),
            }
        except Exception as e:
            logger.error(f"Weather API error: {e}")
            return {
                "error": "weather_api_failed",
                "message": f"Failed to retrieve weather data: {e}",
            }

    def _weather_code_to_condition(self, code: int) -> str:
        """Convert WMO weather code to human-readable condition."""
        return _WMO_CONDITIONS.get(code, "Unknown")

    def _format_message(
        self, location: str, weather_data: dict[str, Any]
    ) -> str:
        """Format a human-readable weather message."""
        date_str = weather_data["date"]
        today = datetime.now().date().isoformat()

        time_phrase = "currently" if date_str == today else f"on {date_str}"

        temp = weather_data["temperature"]
        condition = weather_data["condition"]

        message = (
            f"The weather in {location} {time_phrase} is "
            f"{condition.lower()} with a temperature of {temp}"
        )

        if (
            "temperature_max" in weather_data
            and "temperature_min" in weather_data
        ):
            t_max = weather_data["temperature_max"]
            t_min = weather_data["temperature_min"]
            message += f" (high: {t_max}, low: {t_min})"

        if weather_data.get("precipitation"):
            message += (
                f", precipitation: {weather_data['precipitation']}"
            )

        return message + "."
