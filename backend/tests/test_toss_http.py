import httpx
import pytest

from portfolio_app.services.toss_http import (
    TOSS_DEFAULT_RETRY_AFTER_SECONDS,
    _retry_after_seconds,
    request_with_toss_retry,
)


@pytest.mark.parametrize(
    ("headers", "expected_delay"),
    [
        ({"X-RateLimit-Reset": "0.75"}, 0.75),
        ({"Retry-After": "soon"}, TOSS_DEFAULT_RETRY_AFTER_SECONDS),
        ({"Retry-After": "-1.25"}, 0.0),
    ],
)
def test_retry_after_seconds_parses_rate_limit_headers(headers, expected_delay):
    response = httpx.Response(429, headers=headers)

    assert _retry_after_seconds(response) == expected_delay


@pytest.mark.asyncio
async def test_request_with_toss_retry_retries_429_once():
    sleeps: list[float] = []
    responses = [
        httpx.Response(429, headers={"Retry-After": "0.5"}),
        httpx.Response(200, json={"ok": True}),
    ]

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def handler(request: httpx.Request) -> httpx.Response:
        response = responses.pop(0)
        response.request = request
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await request_with_toss_retry(
            client,
            "GET",
            "https://openapi.tossinvest.com/test",
            sleep=fake_sleep,
        )

    assert response.status_code == 200
    assert sleeps == [0.5]
    assert responses == []
