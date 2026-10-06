"""Use the same fake provider fixtures with both official SDK HTTP libraries."""

import httpx
import httpx2
import pytest


def install_typesafe_fake_http(monkeypatch):
    class SDKFake(httpx2.AsyncBaseTransport):
        def __init__(self, **kwargs):
            self.inner = httpx.AsyncHTTPTransport()

        async def handle_async_request(self, request):
            req = httpx.Request(
                request.method,
                str(request.url),
                headers=request.headers.raw,
                content=await request.aread(),
                extensions=request.extensions,
            )
            response = await self.inner.handle_async_request(req)
            response.request = req
            try:
                return httpx2.Response(
                    response.status_code,
                    headers=response.headers.raw,
                    content=await response.aread(),
                )
            finally:
                await response.aclose()

        async def aclose(self):
            await self.inner.aclose()

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", SDKFake)

    class Client(httpx2.AsyncClient):
        def __init__(self, *args, **kwargs):
            # Keep SDK-owned creation real and preserve SDK runtime type annotations.
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx2.AsyncHTTPTransport()
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx2, "AsyncClient", Client)


@pytest.fixture(autouse=True)
def typesafe_http_fixture(monkeypatch):
    install_typesafe_fake_http(monkeypatch)
