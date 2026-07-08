import httpx


def toss_http_error_detail(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Toss 요청 실패: HTTP {exc.response.status_code} {exc.response.reason_phrase}"
    return f"Toss 요청 실패: {exc.__class__.__name__}"
