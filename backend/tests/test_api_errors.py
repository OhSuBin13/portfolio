import httpx

from portfolio_app.api.errors import toss_http_error_detail


def test_toss_http_error_detail_formats_status_errors_without_body():
    request = httpx.Request("GET", "https://example.test/toss")
    response = httpx.Response(429, request=request)
    error = httpx.HTTPStatusError("failed", request=request, response=response)

    assert toss_http_error_detail(error) == "Toss 요청 실패: HTTP 429 Too Many Requests"


def test_toss_http_error_detail_formats_transport_errors_by_class_name():
    error = httpx.ConnectError("failed")

    assert toss_http_error_detail(error) == "Toss 요청 실패: ConnectError"
