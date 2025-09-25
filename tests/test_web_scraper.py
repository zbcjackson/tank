import asyncio
import pytest
from unittest.mock import Mock, patch
from src.voice_assistant.tools.web_scraper import WebScraperTool


@pytest.mark.asyncio
async def test_web_scraper_tool_info():
    """Test that the tool returns correct info"""
    tool = WebScraperTool()
    info = tool.get_info()

    assert info.name == "web_scraper"
    assert "web urls" in info.description.lower()
    assert len(info.parameters) == 2
    assert info.parameters[0].name == "url"
    assert info.parameters[0].required == True
    assert info.parameters[1].name == "extract_links"
    assert info.parameters[1].required == False


@pytest.mark.asyncio
async def test_web_scraper_invalid_url():
    """Test handling of invalid URLs"""
    tool = WebScraperTool()

    # Test invalid URL format
    result = await tool.execute("not-a-url")
    assert "error" in result
    assert "Invalid URL" in result["error"]

    # Test non-HTTP scheme
    result = await tool.execute("ftp://example.com")
    assert "error" in result
    assert "HTTP" in result["error"]


@pytest.mark.asyncio
async def test_web_scraper_success():
    """Test successful web scraping"""
    tool = WebScraperTool()

    # Mock HTML content
    mock_html = """
    <html>
        <head>
            <title>Test Page</title>
            <meta name="description" content="Test description">
        </head>
        <body>
            <h1>Main Heading</h1>
            <p>This is test content.</p>
            <a href="https://example.com/link1">Link 1</a>
        </body>
    </html>
    """

    # Mock requests response
    mock_response = Mock()
    mock_response.content = mock_html.encode('utf-8')
    mock_response.headers = {'content-type': 'text/html'}
    mock_response.raise_for_status = Mock()

    with patch.object(tool.session, 'get', return_value=mock_response):
        result = await tool.execute("https://example.com")

        assert result["status"] == "success"
        assert result["title"] == "Test Page"
        assert result["meta_description"] == "Test description"
        assert "Main Heading" in result["text_content"]
        assert "This is test content." in result["text_content"]
        assert len(result["headings"]) == 1
        assert result["headings"][0]["text"] == "Main Heading"


@pytest.mark.asyncio
async def test_web_scraper_with_links():
    """Test web scraping with link extraction"""
    tool = WebScraperTool()

    mock_html = """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <a href="https://example.com/link1">Link 1</a>
            <a href="/relative-link">Relative Link</a>
            <a href="mailto:test@example.com">Email Link</a>
        </body>
    </html>
    """

    mock_response = Mock()
    mock_response.content = mock_html.encode('utf-8')
    mock_response.headers = {'content-type': 'text/html'}
    mock_response.raise_for_status = Mock()

    with patch.object(tool.session, 'get', return_value=mock_response):
        result = await tool.execute("https://example.com", extract_links=True)

        assert result["status"] == "success"
        assert "links" in result
        assert len(result["links"]) >= 1
        # Should include absolute URL and converted relative URL
        link_urls = [link["url"] for link in result["links"]]
        assert "https://example.com/link1" in link_urls
        assert "https://example.com/relative-link" in link_urls


@pytest.mark.asyncio
async def test_web_scraper_connection_error():
    """Test handling of connection errors"""
    tool = WebScraperTool()

    from requests.exceptions import ConnectionError

    with patch.object(tool.session, 'get', side_effect=ConnectionError("Connection failed")):
        result = await tool.execute("https://example.com")

        assert "error" in result
        assert "Connection error" in result["error"]


@pytest.mark.asyncio
async def test_web_scraper_non_html_content():
    """Test handling of non-HTML content"""
    tool = WebScraperTool()

    mock_response = Mock()
    mock_response.content = b"This is not HTML content"
    mock_response.headers = {'content-type': 'application/json'}
    mock_response.raise_for_status = Mock()

    with patch.object(tool.session, 'get', return_value=mock_response):
        result = await tool.execute("https://example.com/api.json")

        assert "error" in result
        assert "HTML content" in result["error"]


@pytest.mark.asyncio
async def test_web_scraper_content_truncation():
    """Test that very long content gets truncated"""
    tool = WebScraperTool(max_content_length=100)  # Set small limit for testing

    # Create HTML with very long content
    long_content = "This is very long content. " * 100
    mock_html = f"""
    <html>
        <head><title>Long Page</title></head>
        <body><p>{long_content}</p></body>
    </html>
    """

    mock_response = Mock()
    mock_response.content = mock_html.encode('utf-8')
    mock_response.headers = {'content-type': 'text/html'}
    mock_response.raise_for_status = Mock()

    with patch.object(tool.session, 'get', return_value=mock_response):
        result = await tool.execute("https://example.com")

        assert result["status"] == "success"
        assert len(result["text_content"]) <= 130  # 100 + some buffer for truncation message
        assert "[Content truncated]" in result["text_content"]


if __name__ == "__main__":
    # Run a simple test
    async def run_test():
        tool = WebScraperTool()
        info = tool.get_info()
        print(f"Tool name: {info.name}")
        print(f"Tool description: {info.description}")
        print(f"Tool parameters: {[p.name for p in info.parameters]}")

        # Test invalid URL
        result = await tool.execute("invalid-url")
        print(f"Invalid URL result: {result}")

    asyncio.run(run_test())