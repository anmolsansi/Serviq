from __future__ import annotations

import ipaddress
import socket
import ssl
from collections.abc import Sequence
from typing import Any

import pytest

from app.core import public_knowledge_fetch as m


class FakeSocket:
    def __init__(self, peer: str) -> None:
        self.peer = peer

    def getpeername(self) -> tuple[str, int]:
        return self.peer, 443


class FakeResponse:
    def __init__(
        self, status: int = 200, headers: dict[str, str] | None = None, body: bytes = b"ok"
    ) -> None:
        self.status = status
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}
        self.body = body
        self.offset = 0

    def getheader(self, name: str) -> str | None:
        return self.headers.get(name.lower())

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class FakeConnection:
    def __init__(
        self, peer: str, response: FakeResponse, *, request_error: BaseException | None = None
    ) -> None:
        self.sock = FakeSocket(peer)
        self.response = response
        self.request_error = request_error
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.closed = False

    def connect(self) -> None:
        if self.request_error is not None:
            raise self.request_error

    def request(self, method: str, target: str, headers: dict[str, str]) -> None:
        self.requests.append((method, target, headers))

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def policy(
    *hosts: str, max_bytes: int = 1024, timeout: float = 1.0
) -> m.PublicKnowledgeFetchPolicy:
    return m.PublicKnowledgeFetchPolicy(
        frozenset(hosts), max_response_bytes=max_bytes, timeout_seconds=timeout
    )


def patch_network(
    monkeypatch: pytest.MonkeyPatch,
    dns: dict[str, tuple[str, ...]],
    responses: Sequence[tuple[str, FakeResponse | BaseException]],
) -> list[FakeConnection]:
    response_queue = list(responses)

    def resolve(host: str) -> tuple[m.IPAddress, ...]:
        values = dns.get(host)
        if values is None:
            raise m.PublicKnowledgeFetchError(
                m.PublicKnowledgeFetchErrorCode.DNS_FAILURE, retryable=True
            )
        return tuple(ipaddress.ip_address(value) for value in values)

    made: list[FakeConnection] = []

    def connect(host: str, connect_ip: str, timeout: float) -> FakeConnection:
        del host, timeout
        peer, response_or_error = response_queue.pop(0)
        assert connect_ip in dns.get("example.com", ()) + dns.get("redirect.example.com", ())
        response = (
            response_or_error if isinstance(response_or_error, FakeResponse) else FakeResponse()
        )
        request_error = response_or_error if isinstance(response_or_error, BaseException) else None
        conn = FakeConnection(peer, response, request_error=request_error)
        made.append(conn)
        return conn

    monkeypatch.setattr(m, "_resolve_host", resolve)
    monkeypatch.setattr(m, "_new_connection", connect)
    return made


def assert_code(
    error: pytest.ExceptionInfo[m.PublicKnowledgeFetchError],
    code: m.PublicKnowledgeFetchErrorCode,
    retryable: bool = False,
) -> None:
    assert error.value.code == code
    assert error.value.retryable is retryable
    assert str(error.value) == code.value


def test_public_success(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(headers={"Content-Type": "text/plain; charset=utf-8"}, body=b"hello")
    connections = patch_network(
        monkeypatch, {"example.com": ("93.184.216.34",)}, [("93.184.216.34", response)]
    )
    result = m.fetch_public_knowledge("https://example.com/a%20b?q=x%20y", policy("example.com"))
    assert result.final_url == "https://example.com/a%20b?q=x%20y"
    assert result.status_code == 200
    assert result.content_type == "text/plain"
    assert result.body == b"hello"
    method, target, headers = connections[0].requests[0]
    assert method == "GET"
    assert target == "/a%20b?q=x%20y"
    assert headers["Accept-Encoding"] == "identity"


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "100.64.0.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "2001:db8::1",
        "0.0.0.0",
    ],
)
def test_non_global_addresses_are_blocked(address: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(
        *args: Any, **kwargs: Any
    ) -> list[tuple[int, int, int, str, tuple[Any, ...]]]:
        del args, kwargs
        family = 10 if ":" in address else 2
        return [
            (
                family,
                1,
                6,
                "",
                (address, 443, 0, 0) if family == 10 else (address, 443),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m._resolve_host("example.com")
    assert_code(error, m.PublicKnowledgeFetchErrorCode.BLOCKED_ADDRESS)


def test_mixed_public_private_dns_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(
        *args: Any, **kwargs: Any
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        del args, kwargs
        return [
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m._resolve_host("example.com")
    assert_code(error, m.PublicKnowledgeFetchErrorCode.BLOCKED_ADDRESS)


@pytest.mark.parametrize(
    "url,code",
    [
        ("http://example.com", m.PublicKnowledgeFetchErrorCode.INVALID_URL),
        ("https://user:pass@example.com", m.PublicKnowledgeFetchErrorCode.INVALID_URL),
        ("https://example.com/#x", m.PublicKnowledgeFetchErrorCode.INVALID_URL),
        ("https://example.com:8443/", m.PublicKnowledgeFetchErrorCode.INVALID_URL),
        (" example.com", m.PublicKnowledgeFetchErrorCode.INVALID_URL),
        ("https://other.example.com/", m.PublicKnowledgeFetchErrorCode.DOMAIN_NOT_ALLOWED),
    ],
)
def test_url_rejections(url: str, code: m.PublicKnowledgeFetchErrorCode) -> None:
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge(url, policy("example.com"))
    assert_code(error, code)


def test_allowed_public_redirect_is_revalidated(monkeypatch: pytest.MonkeyPatch) -> None:
    first = FakeResponse(status=302, headers={"Location": "https://redirect.example.com/final"})
    second = FakeResponse(headers={"Content-Type": "text/html"}, body=b"<p>ok</p>")
    patch_network(
        monkeypatch,
        {
            "example.com": ("93.184.216.34",),
            "redirect.example.com": ("142.250.72.14",),
        },
        [("93.184.216.34", first), ("142.250.72.14", second)],
    )
    result = m.fetch_public_knowledge(
        "https://example.com/start", policy("example.com", "redirect.example.com")
    )
    assert result.final_url == "https://redirect.example.com/final"
    assert result.body == b"<p>ok</p>"


def test_redirect_to_private_fails_before_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    first = FakeResponse(status=302, headers={"Location": "https://redirect.example.com/final"})
    connections = patch_network(
        monkeypatch,
        {
            "example.com": ("93.184.216.34",),
            "redirect.example.com": ("127.0.0.1",),
        },
        [("93.184.216.34", first)],
    )
    original = m._resolve_host

    def resolve(host: str) -> tuple[m.IPAddress, ...]:
        addrs = original(host)
        if any(not m._is_allowed_address(address) for address in addrs):
            raise m.PublicKnowledgeFetchError(m.PublicKnowledgeFetchErrorCode.BLOCKED_ADDRESS)
        return addrs

    monkeypatch.setattr(m, "_resolve_host", resolve)
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge(
            "https://example.com/start", policy("example.com", "redirect.example.com")
        )
    assert_code(error, m.PublicKnowledgeFetchErrorCode.BLOCKED_ADDRESS)
    assert len(connections) == 1


def test_redirect_to_unallowlisted_host_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    first = FakeResponse(status=302, headers={"Location": "https://evil.example.net/final"})
    patch_network(
        monkeypatch, {"example.com": ("93.184.216.34",)}, [("93.184.216.34", first)]
    )
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/start", policy("example.com"))
    assert_code(error, m.PublicKnowledgeFetchErrorCode.DOMAIN_NOT_ALLOWED)


def test_redirect_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    redirects = [
        ("93.184.216.34", FakeResponse(status=302, headers={"Location": "/again"}))
        for _ in range(6)
    ]
    patch_network(monkeypatch, {"example.com": ("93.184.216.34",)}, redirects)
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/start", policy("example.com"))
    assert_code(error, m.PublicKnowledgeFetchErrorCode.TOO_MANY_REDIRECTS)


def test_redirect_without_location(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_network(
        monkeypatch,
        {"example.com": ("93.184.216.34",)},
        [("93.184.216.34", FakeResponse(status=302))],
    )
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/start", policy("example.com"))
    assert_code(error, m.PublicKnowledgeFetchErrorCode.REDIRECT_MISSING_LOCATION)


@pytest.mark.parametrize(
    "headers,code",
    [
        (
            {"Content-Type": "application/octet-stream"},
            m.PublicKnowledgeFetchErrorCode.UNSUPPORTED_MIME,
        ),
        (
            {"Content-Type": "text/plain", "Content-Encoding": "gzip"},
            m.PublicKnowledgeFetchErrorCode.UNSUPPORTED_ENCODING,
        ),
        (
            {"Content-Type": "text/plain", "Content-Length": "not-a-number"},
            m.PublicKnowledgeFetchErrorCode.INVALID_RESPONSE,
        ),
    ],
)
def test_response_metadata_rejections(
    headers: dict[str, str],
    code: m.PublicKnowledgeFetchErrorCode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_network(
        monkeypatch,
        {"example.com": ("93.184.216.34",)},
        [("93.184.216.34", FakeResponse(headers=headers))],
    )
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/", policy("example.com"))
    assert_code(error, code)


def test_declared_oversize_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(
        headers={"Content-Type": "text/plain", "Content-Length": "11"}, body=b"x"
    )
    patch_network(
        monkeypatch, {"example.com": ("93.184.216.34",)}, [("93.184.216.34", response)]
    )
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/", policy("example.com", max_bytes=10))
    assert_code(error, m.PublicKnowledgeFetchErrorCode.RESPONSE_TOO_LARGE)
    assert response.offset == 0


def test_streamed_oversize_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(headers={"Content-Type": "text/plain"}, body=b"01234567890")
    patch_network(
        monkeypatch, {"example.com": ("93.184.216.34",)}, [("93.184.216.34", response)]
    )
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/", policy("example.com", max_bytes=10))
    assert_code(error, m.PublicKnowledgeFetchErrorCode.RESPONSE_TOO_LARGE)


def test_peer_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(headers={"Content-Type": "text/plain"})
    connections = patch_network(
        monkeypatch, {"example.com": ("93.184.216.34",)}, [("1.1.1.1", response)]
    )
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/", policy("example.com"))
    assert_code(error, m.PublicKnowledgeFetchErrorCode.PEER_MISMATCH)
    assert connections[0].requests == []


@pytest.mark.parametrize(
    "status,retryable",
    [(404, False), (408, True), (425, True), (429, True), (500, True), (503, True)],
)
def test_http_status_retryability(
    status: int, retryable: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_network(
        monkeypatch,
        {"example.com": ("93.184.216.34",)},
        [("93.184.216.34", FakeResponse(status=status, body=b"SECRET BODY"))],
    )
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/", policy("example.com"))
    assert_code(error, m.PublicKnowledgeFetchErrorCode.HTTP_STATUS, retryable)
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize(
    "raised,code",
    [
        (TimeoutError(), m.PublicKnowledgeFetchErrorCode.TIMEOUT),
        (ssl.SSLError("secret tls detail"), m.PublicKnowledgeFetchErrorCode.TLS_FAILURE),
        (OSError("secret target detail"), m.PublicKnowledgeFetchErrorCode.NETWORK_FAILURE),
    ],
)
def test_transport_errors_are_safe(
    raised: BaseException,
    code: m.PublicKnowledgeFetchErrorCode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_network(
        monkeypatch, {"example.com": ("93.184.216.34",)}, [("93.184.216.34", raised)]
    )
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/", policy("example.com"))
    assert_code(error, code, True)
    assert "secret" not in str(error.value).lower()


def test_dns_failure_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise socket.gaierror("secret dns detail")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(m.PublicKnowledgeFetchError) as error:
        m.fetch_public_knowledge("https://example.com/", policy("example.com"))
    assert_code(error, m.PublicKnowledgeFetchErrorCode.DNS_FAILURE, True)
    assert "secret" not in str(error.value).lower()


@pytest.mark.parametrize(
    "args",
    [
        {"allowed_hosts": frozenset()},
        {"allowed_hosts": frozenset({"*.example.com"})},
        {"allowed_hosts": frozenset({"example.com"}), "max_response_bytes": 0},
        {
            "allowed_hosts": frozenset({"example.com"}),
            "max_response_bytes": m.HARD_MAX_RESPONSE_BYTES + 1,
        },
        {"allowed_hosts": frozenset({"example.com"}), "timeout_seconds": 0},
        {
            "allowed_hosts": frozenset({"example.com"}),
            "timeout_seconds": m.HARD_MAX_TIMEOUT_SECONDS + 0.1,
        },
    ],
)
def test_policy_bounds(args: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        m.PublicKnowledgeFetchPolicy(**args)


def test_hostname_normalization() -> None:
    p = policy("EXAMPLE.COM.")
    assert p.allowed_hosts == frozenset({"example.com"})
