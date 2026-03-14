from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from tank_backend.tools.weather import WeatherTool

# Use relative dates so tests don't break when "today" matches a fixture date.
_TODAY = date.today()
_YESTERDAY = (_TODAY - timedelta(days=1)).isoformat()
_TOMORROW = (_TODAY + timedelta(days=1)).isoformat()
_DAY_AFTER = (_TODAY + timedelta(days=2)).isoformat()
_TODAY_ISO = _TODAY.isoformat()


@pytest.fixture
def weather_tool():
    return WeatherTool()


@pytest.fixture
def mock_geocode_response():
    return {
        "results": [
            {
                "name": "New York",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "country": "United States",
                "admin1": "New York",
            }
        ]
    }


@pytest.fixture
def mock_current_weather_response():
    return {
        "current": {
            "temperature_2m": 22.5,
            "relative_humidity_2m": 65,
            "weathercode": 0,
            "windspeed_10m": 12.3,
        },
        "daily": {
            "time": ["2026-03-12"],
            "temperature_2m_max": [25.0],
            "temperature_2m_min": [18.0],
            "weathercode": [0],
            "precipitation_sum": [0.0],
            "windspeed_10m_max": [15.0],
        },
    }


@pytest.fixture
def mock_forecast_weather_response():
    return {
        "daily": {
            "time": [_TODAY_ISO, _TOMORROW, _DAY_AFTER],
            "temperature_2m_max": [25.0, 23.0, 21.0],
            "temperature_2m_min": [18.0, 17.0, 16.0],
            "weathercode": [0, 2, 61],
            "precipitation_sum": [0.0, 0.5, 5.2],
            "windspeed_10m_max": [15.0, 18.0, 22.0],
        }
    }


class TestWeatherTool:
    def test_get_info(self, weather_tool):
        """Test tool info returns correct metadata"""
        info = weather_tool.get_info()

        assert info.name == "get_weather"
        assert "weather information" in info.description.lower()
        assert len(info.parameters) == 2

        # Check location parameter
        location_param = next(p for p in info.parameters if p.name == "location")
        assert location_param.required is True
        assert location_param.type == "string"

        # Check date parameter
        date_param = next(p for p in info.parameters if p.name == "date")
        assert date_param.required is False
        assert date_param.type == "string"

    @pytest.mark.asyncio
    async def test_current_weather_success(
        self, weather_tool, mock_geocode_response, mock_current_weather_response
    ):
        """Test getting current weather for a location"""
        with patch("requests.get") as mock_get:
            # Mock geocoding response
            mock_geocode = MagicMock()
            mock_geocode.json.return_value = mock_geocode_response
            mock_geocode.raise_for_status = MagicMock()

            # Mock weather API response
            mock_weather = MagicMock()
            mock_weather.json.return_value = mock_current_weather_response
            mock_weather.raise_for_status = MagicMock()

            # Return different responses for geocoding and weather API
            mock_get.side_effect = [mock_geocode, mock_weather]

            result = await weather_tool.execute(location="New York")

            assert "error" not in result
            assert result["location"] == "New York"
            assert result["coordinates"]["latitude"] == 40.7128
            assert result["coordinates"]["longitude"] == -74.0060
            assert result["temperature"] == "22.5°C"
            assert result["condition"] == "Clear sky"
            assert result["humidity"] == "65%"
            assert result["wind_speed"] == "12.3 km/h"
            assert "New York" in result["message"]
            assert "currently" in result["message"]

    @pytest.mark.asyncio
    async def test_forecast_weather_success(
        self, weather_tool, mock_geocode_response, mock_forecast_weather_response
    ):
        """Test getting forecast weather for a future date"""
        with patch("requests.get") as mock_get:
            mock_geocode = MagicMock()
            mock_geocode.json.return_value = mock_geocode_response
            mock_geocode.raise_for_status = MagicMock()

            mock_weather = MagicMock()
            mock_weather.json.return_value = mock_forecast_weather_response
            mock_weather.raise_for_status = MagicMock()

            mock_get.side_effect = [mock_geocode, mock_weather]

            result = await weather_tool.execute(location="New York", date=_DAY_AFTER)

            assert "error" not in result
            assert result["location"] == "New York"
            assert result["date"] == _DAY_AFTER
            assert result["temperature_max"] == "21.0°C"
            assert result["temperature_min"] == "16.0°C"
            assert result["condition"] == "Slight rain"
            assert result["precipitation"] == "5.2 mm"
            assert _DAY_AFTER in result["message"]

    @pytest.mark.asyncio
    async def test_location_not_found(self, weather_tool):
        """Test handling of location not found"""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"results": []}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await weather_tool.execute(location="NonexistentCity12345")

            assert "error" in result
            assert result["error"] == "location_not_found"
            assert "NonexistentCity12345" in result["message"]

    @pytest.mark.asyncio
    async def test_invalid_date_format(self, weather_tool, mock_geocode_response):
        """Test handling of invalid date format"""
        with patch("requests.get") as mock_get:
            mock_geocode = MagicMock()
            mock_geocode.json.return_value = mock_geocode_response
            mock_geocode.raise_for_status = MagicMock()

            # Mock weather API to raise ValueError for invalid date
            mock_weather = MagicMock()
            mock_weather.json.side_effect = ValueError("Invalid date")
            mock_weather.raise_for_status = MagicMock()

            mock_get.side_effect = [mock_geocode, mock_weather]

            result = await weather_tool.execute(location="New York", date="invalid-date")

            assert "error" in result
            assert "YYYY-MM-DD" in result["message"]

    @pytest.mark.asyncio
    async def test_geocoding_api_error(self, weather_tool):
        """Test handling of geocoding API errors"""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("Network error")

            result = await weather_tool.execute(location="New York")

            assert "error" in result
            assert "New York" in result["message"]

    @pytest.mark.asyncio
    async def test_weather_api_error(self, weather_tool, mock_geocode_response):
        """Test handling of weather API errors"""
        with patch("requests.get") as mock_get:
            mock_geocode = MagicMock()
            mock_geocode.json.return_value = mock_geocode_response
            mock_geocode.raise_for_status = MagicMock()

            mock_weather = MagicMock()
            mock_weather.side_effect = Exception("Weather API error")

            mock_get.side_effect = [mock_geocode, mock_weather]

            result = await weather_tool.execute(location="New York")

            assert "error" in result

    def test_weather_code_to_condition(self, weather_tool):
        """Test weather code conversion"""
        assert weather_tool._weather_code_to_condition(0) == "Clear sky"
        assert weather_tool._weather_code_to_condition(1) == "Mainly clear"
        assert weather_tool._weather_code_to_condition(2) == "Partly cloudy"
        assert weather_tool._weather_code_to_condition(3) == "Overcast"
        assert weather_tool._weather_code_to_condition(45) == "Foggy"
        assert weather_tool._weather_code_to_condition(61) == "Slight rain"
        assert weather_tool._weather_code_to_condition(63) == "Moderate rain"
        assert weather_tool._weather_code_to_condition(65) == "Heavy rain"
        assert weather_tool._weather_code_to_condition(71) == "Slight snow"
        assert weather_tool._weather_code_to_condition(95) == "Thunderstorm"
        assert weather_tool._weather_code_to_condition(999) == "Unknown"

    def test_format_message_current(self, weather_tool):
        """Test message formatting for current weather"""
        weather_data = {
            "date": "2026-03-12",
            "temperature": "22.5°C",
            "condition": "Clear sky",
            "humidity": "65%",
            "wind_speed": "12.3 km/h",
        }

        with patch("tank_backend.tools.weather.datetime") as mock_datetime:
            mock_datetime.now.return_value.date.return_value.isoformat.return_value = (
                "2026-03-12"
            )

            message = weather_tool._format_message("New York", weather_data)

            assert "New York" in message
            assert "currently" in message
            assert "clear sky" in message.lower()
            assert "22.5°C" in message

    def test_format_message_forecast(self, weather_tool):
        """Test message formatting for forecast weather"""
        weather_data = {
            "date": "2026-03-14",
            "temperature": "21.5°C",
            "temperature_max": "25.0°C",
            "temperature_min": "18.0°C",
            "condition": "Partly cloudy",
            "precipitation": "2.5 mm",
        }

        with patch("tank_backend.tools.weather.datetime") as mock_datetime:
            mock_datetime.now.return_value.date.return_value.isoformat.return_value = (
                "2026-03-12"
            )

            message = weather_tool._format_message("Tokyo", weather_data)

            assert "Tokyo" in message
            assert "2026-03-14" in message
            assert "partly cloudy" in message.lower()
            assert "high: 25.0°C" in message
            assert "low: 18.0°C" in message
            assert "precipitation: 2.5 mm" in message

    @pytest.mark.asyncio
    async def test_geocode_location_success(self, weather_tool, mock_geocode_response):
        """Test successful geocoding"""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_geocode_response
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = weather_tool._geocode_location("New York")

            assert "error" not in result
            assert result["name"] == "New York"
            assert result["latitude"] == 40.7128
            assert result["longitude"] == -74.0060
            assert result["country"] == "United States"

    @pytest.mark.asyncio
    async def test_get_weather_data_current(
        self, weather_tool, mock_current_weather_response
    ):
        """Test getting current weather data"""
        from datetime import date

        with patch("requests.get") as mock_get, patch(
            "tank_backend.tools.weather.datetime"
        ) as mock_datetime:
            # Mock datetime.now() to return today's date
            today = date(2026, 3, 12)
            mock_datetime.now.return_value.date.return_value = today

            # Mock datetime.strptime() to parse the date string
            mock_datetime.strptime.return_value.date.return_value = today

            mock_response = MagicMock()
            mock_response.json.return_value = mock_current_weather_response
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = weather_tool._get_weather_data(40.7128, -74.0060, "2026-03-12")

            assert "error" not in result
            assert result["date"] == "2026-03-12"
            assert result["temperature"] == "22.5°C"
            assert result["condition"] == "Clear sky"
