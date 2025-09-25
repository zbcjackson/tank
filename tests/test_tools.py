import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from src.voice_assistant.tools.manager import ToolManager, WeatherTool, TimeTool, CalculatorTool

class TestToolManager:
    @pytest.fixture
    def tool_manager(self):
        # Tool manager without API key (no web search)
        return ToolManager()

    @pytest.fixture
    def tool_manager_with_search(self):
        # Tool manager with API key (includes web search)
        return ToolManager(serper_api_key="test_api_key")

    def test_tool_registration(self, tool_manager):
        assert "get_weather" in tool_manager.tools
        assert "get_time" in tool_manager.tools
        assert "calculate" in tool_manager.tools
        # Web search should not be available without API key
        assert "web_search" not in tool_manager.tools

    def test_tool_registration_with_search(self, tool_manager_with_search):
        assert "get_weather" in tool_manager_with_search.tools
        assert "get_time" in tool_manager_with_search.tools
        assert "calculate" in tool_manager_with_search.tools
        assert "web_search" in tool_manager_with_search.tools

    def test_get_tool_info(self, tool_manager):
        info_list = tool_manager.get_tool_info()
        assert len(info_list) == 4  # Without web search (weather, time, calculator, web_scraper)
        assert any(tool.name == "get_weather" for tool in info_list)
        assert not any(tool.name == "web_search" for tool in info_list)

    def test_get_tool_info_with_search(self, tool_manager_with_search):
        info_list = tool_manager_with_search.get_tool_info()
        assert len(info_list) == 5  # With web search (weather, time, calculator, web_scraper, web_search)
        assert any(tool.name == "get_weather" for tool in info_list)
        assert any(tool.name == "web_search" for tool in info_list)

    @pytest.mark.asyncio
    async def test_calculator_tool(self, tool_manager):
        result = await tool_manager.execute_tool("calculate", expression="2 + 2")
        assert result["result"] == 4
        assert result["expression"] == "2 + 2"

    @pytest.mark.asyncio
    async def test_calculator_tool_error(self, tool_manager):
        result = await tool_manager.execute_tool("calculate", expression="invalid")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_time_tool(self, tool_manager):
        result = await tool_manager.execute_tool("get_time")
        assert "current_time" in result
        assert "message" in result

    @pytest.mark.asyncio
    async def test_weather_tool(self, tool_manager):
        result = await tool_manager.execute_tool("get_weather", location="New York")
        assert result["location"] == "New York"
        assert "temperature" in result

    @pytest.mark.asyncio
    async def test_nonexistent_tool(self, tool_manager):
        result = await tool_manager.execute_tool("nonexistent_tool")
        assert "error" in result
        assert "available_tools" in result

    def test_parse_tool_call(self, tool_manager):
        result = tool_manager.parse_tool_call("get_weather(New York)")
        assert result is not None
        assert result["tool_name"] == "get_weather"

        result = tool_manager.parse_tool_call("calculate(2 + 2)")
        assert result is not None
        assert result["tool_name"] == "calculate"

        result = tool_manager.parse_tool_call("nonexistent_tool()")
        assert result is None

    @pytest.mark.asyncio
    async def test_web_search_tool(self, tool_manager_with_search):
        # Test that the tool can be called (mock the response since we don't want to make real web requests in tests)
        with patch('requests.post') as mock_post:
            # Mock the Serper API response
            mock_response = Mock()
            mock_response.json.return_value = {
                "organic": [{
                    "title": "Test Title",
                    "snippet": "Test search result from Serper",
                    "link": "https://example.com"
                }]
            }
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            result = await tool_manager_with_search.execute_tool("web_search", query="test query")
            assert "answer" in result
            assert result["query"] == "test query"
            assert result["source"] == "Serper (Google Search)"