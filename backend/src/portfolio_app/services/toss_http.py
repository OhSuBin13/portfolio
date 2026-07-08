import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

TOSS_MAX_RETRIES = 1
TOSS_DEFAULT_RETRY_AFTER_SECONDS = 1.0
TOSS_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60.0
TOSS_DEFAULT_TOKEN_EXPIRES_IN_SECONDS = 3600.0

Sleep = Callable[[float], Awaitable[None]]
Now = Callable[[], float]


def _retry_after_seconds(response: httpx.Response) -> float:
    header_value = response.headers.get("Retry-After") or response.headers.get(
        "X-RateLimit-Reset"
    )
    if header_value is None:
        return TOSS_DEFAULT_RETRY_AFTER_SECONDS

    try:
        delay = float(header_value)
    except ValueError:
        return TOSS_DEFAULT_RETRY_AFTER_SECONDS
    return max(delay, 0.0)


async def request_with_toss_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    sleep: Sleep = asyncio.sleep,
    max_retries: int = TOSS_MAX_RETRIES,
    **kwargs: object,
) -> httpx.Response:
    response = await client.request(method, url, **kwargs)
    for _attempt in range(max_retries):
        if response.status_code != 429:
            return response
        await sleep(_retry_after_seconds(response))
        response = await client.request(method, url, **kwargs)
    return response


class TossAuthClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = "https://openapi.tossinvest.com",
        sleep: Sleep = asyncio.sleep,
        now: Now = time.monotonic,
    ) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._now = now
        self._token_lock = asyncio.Lock()
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0

    def _has_fresh_access_token(self) -> bool:
        return (
            self._access_token is not None
            and self._now() < self._access_token_expires_at
        )

    async def token(self) -> str:
        if self._has_fresh_access_token():
            assert self._access_token is not None
            return self._access_token

        async with self._token_lock:
            if self._has_fresh_access_token():
                assert self._access_token is not None
                return self._access_token

            if not self.client_id or not self.client_secret:
                raise ValueError("Toss API 인증 정보가 필요합니다.")

            async with httpx.AsyncClient(timeout=10) as client:
                response = await request_with_toss_retry(
                    client,
                    "POST",
                    f"{self.base_url}/oauth2/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    sleep=self._sleep,
                )
                response.raise_for_status()
                payload = response.json()

            access_token = payload.get("access_token") if isinstance(payload, dict) else None
            if not isinstance(access_token, str) or not access_token.strip():
                raise ValueError("Toss 토큰 응답에서 access_token을 찾을 수 없습니다.")

            expires_in = _token_expires_in_seconds(payload)
            refresh_margin = min(
                TOSS_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS,
                expires_in / 2,
            )
            self._access_token = access_token.strip()
            self._access_token_expires_at = self._now() + max(expires_in - refresh_margin, 0.0)
            return self._access_token


def _token_expires_in_seconds(payload: dict[str, Any]) -> float:
    try:
        expires_in = float(payload.get("expires_in"))
    except (TypeError, ValueError):
        return TOSS_DEFAULT_TOKEN_EXPIRES_IN_SECONDS
    if not math.isfinite(expires_in) or expires_in < 0:
        return TOSS_DEFAULT_TOKEN_EXPIRES_IN_SECONDS
    return expires_in
