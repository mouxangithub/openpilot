from webui.server.run_server import build_https_redirect_location, format_http_redirect_response


def test_build_https_redirect_location_with_host_header() -> None:
  loc = build_https_redirect_location(
    "GET /settings HTTP/1.1",
    ["Host: 10.255.128.121", ""],
    public_port=5080,
  )
  assert loc == "https://10.255.128.121:5080/settings"


def test_build_https_redirect_location_without_host_header() -> None:
  loc = build_https_redirect_location("GET / HTTP/1.1", [], public_port=5080)
  assert loc == "https://localhost:5080/"


def test_format_http_redirect_response() -> None:
  body = format_http_redirect_response("https://example.com/")
  assert b"301 Moved Permanently" in body
  assert b"Location: https://example.com/" in body
