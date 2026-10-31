"""Credential-bearing HTTP never follows redirects, including redirects of signed bulk URLs."""

from urllib.parse import urljoin, urlsplit
import urllib.request


class RedirectError(ValueError):
    """An endpoint must be configured with its final URL. Only the destination origin is public."""

    def __init__(self, code, origin):
        self.code = code
        super().__init__(f"Server returned HTTP {code} redirect to {origin}; use the final URL")


def _origin(request_url, location):
    try:
        parsed = urlsplit(urljoin(request_url, location))
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return "<invalid origin>"
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        return f"{parsed.scheme}://{host}" + (f":{parsed.port}" if parsed.port is not None else "")
    except ValueError:
        return "<invalid origin>"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def http_response(self, request, response):
        # Check every 3xx before urllib's HTTPErrorProcessor or method-dependent redirect logic runs.
        if 300 <= response.code < 400:
            origin = _origin(request.full_url, response.headers.get("Location", ""))
            response.close()
            raise RedirectError(response.code, origin)
        return response

    https_response = http_response

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def opener(*, proxy=False):
    """A new opener; only researcher clients opt into the system proxy configuration."""
    return urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler(None if proxy else {}))
