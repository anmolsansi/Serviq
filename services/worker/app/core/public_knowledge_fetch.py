"""SSRF-safe HTTPS fetch boundary for explicitly approved public knowledge sources."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import SplitResult, quote, urljoin, urlsplit

DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
HARD_MAX_RESPONSE_BYTES = 50 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 10.0
HARD_MAX_TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 5
READ_CHUNK_BYTES = 64 * 1024
USER_AGENT = "ServiqKnowledgeFetcher/1.0"
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "text/markdown",
        "application/xml",
        "text/xml",
        "application/rss+xml",
        "application/atom+xml",
    }
)
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429})
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class PublicKnowledgeFetchErrorCode(StrEnum):
    INVALID_URL = "PUBLIC_FETCH_INVALID_URL"
    DOMAIN_NOT_ALLOWED = "PUBLIC_FETCH_DOMAIN_NOT_ALLOWED"
    DNS_FAILURE = "PUBLIC_FETCH_DNS_FAILURE"
    BLOCKED_ADDRESS = "PUBLIC_FETCH_BLOCKED_ADDRESS"
    PEER_MISMATCH = "PUBLIC_FETCH_PEER_MISMATCH"
    TOO_MANY_REDIRECTS = "PUBLIC_FETCH_TOO_MANY_REDIRECTS"
    REDIRECT_MISSING_LOCATION = "PUBLIC_FETCH_REDIRECT_MISSING_LOCATION"
    HTTP_STATUS = "PUBLIC_FETCH_HTTP_STATUS"
    UNSUPPORTED_MIME = "PUBLIC_FETCH_UNSUPPORTED_MIME"
    UNSUPPORTED_ENCODING = "PUBLIC_FETCH_UNSUPPORTED_ENCODING"
    RESPONSE_TOO_LARGE = "PUBLIC_FETCH_RESPONSE_TOO_LARGE"
    INVALID_RESPONSE = "PUBLIC_FETCH_INVALID_RESPONSE"
    TIMEOUT = "PUBLIC_FETCH_TIMEOUT"
    TLS_FAILURE = "PUBLIC_FETCH_TLS_FAILURE"
    NETWORK_FAILURE = "PUBLIC_FETCH_NETWORK_FAILURE"


class PublicKnowledgeFetchError(RuntimeError):
    """Safe typed failure that never includes raw remote or transport details."""

    def __init__(self, code: PublicKnowledgeFetchErrorCode, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class PublicKnowledgeFetchResult:
    final_url: str
    status_code: int
    content_type: str
    body: bytes


def _normalize_host(host: str) -> str:
    candidate = host.strip().rstrip(".")
    invalid = not candidate or "*" in candidate or "/" in candidate or "://" in candidate
    invalid = invalid or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in candidate
    )
    if invalid:
        raise ValueError("allowed host must be an exact hostname")
    try:
        return candidate.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("allowed host is invalid") from error


@dataclass(frozen=True, slots=True)
class PublicKnowledgeFetchPolicy:
    allowed_hosts: frozenset[str]
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not self.allowed_hosts:
            raise ValueError("allowed_hosts must not be empty")
        normalized = frozenset(_normalize_host(host) for host in self.allowed_hosts)
        if not 1 <= self.max_response_bytes <= HARD_MAX_RESPONSE_BYTES:
            raise ValueError("max_response_bytes is outside the frozen V1 bounds")
        if not 0 < self.timeout_seconds <= HARD_MAX_TIMEOUT_SECONDS:
            raise ValueError("timeout_seconds is outside the frozen V1 bounds")
        object.__setattr__(self, "allowed_hosts", normalized)


def _validate_url(url: str, policy: PublicKnowledgeFetchPolicy) -> tuple[SplitResult, str]:
    invalid = not url or url != url.strip() or "#" in url
    invalid = invalid or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)
    if invalid:
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.INVALID_URL)
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
        has_credentials = parsed.username is not None or parsed.password is not None
    except ValueError:
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.INVALID_URL) from None
    if parsed.scheme.lower() != "https" or not parsed.netloc or host is None or has_credentials:
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.INVALID_URL)
    if port not in (None, 443):
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.INVALID_URL)
    try:
        normalized_host = _normalize_host(host)
    except ValueError:
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.INVALID_URL) from None
    if normalized_host not in policy.allowed_hosts:
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.DOMAIN_NOT_ALLOWED)
    return parsed, normalized_host


def _is_allowed_address(address: IPAddress) -> bool:
    return (
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def _resolve_host(host: str) -> tuple[IPAddress, ...]:
    try:
        records = socket.getaddrinfo(
            host, 443, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror:
        raise PublicKnowledgeFetchError(
            PublicKnowledgeFetchErrorCode.DNS_FAILURE, retryable=True
        ) from None
    addresses: list[IPAddress] = []
    for record in records:
        try:
            address = ipaddress.ip_address(record[4][0])
        except ValueError:
            raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.BLOCKED_ADDRESS) from None
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.DNS_FAILURE, retryable=True)
    if any(not _is_allowed_address(address) for address in addresses):
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.BLOCKED_ADDRESS)
    return tuple(addresses)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Dial one validated IP while preserving hostname TLS verification."""

    def __init__(self, host: str, connect_ip: str, timeout: float) -> None:
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._connect_ip = connect_ip

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._connect_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _new_connection(host: str, connect_ip: str, timeout: float) -> _PinnedHTTPSConnection:
    return _PinnedHTTPSConnection(host, connect_ip, timeout)


def _request_target(parsed: SplitResult) -> str:
    path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    if not parsed.query:
        return path
    query = quote(parsed.query, safe="=&?/%:@!$'()*+,;=-._~")
    return f"{path}?{query}"


def _read_success_body(
    response: http.client.HTTPResponse, max_response_bytes: int
) -> tuple[str, bytes]:
    encoding = response.getheader("Content-Encoding")
    if encoding is not None and encoding.strip().lower() not in {"", "identity"}:
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.UNSUPPORTED_ENCODING)
    raw_type = response.getheader("Content-Type")
    content_type = "" if raw_type is None else raw_type.split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.UNSUPPORTED_MIME)
    raw_length = response.getheader("Content-Length")
    if raw_length is not None:
        try:
            length = int(raw_length, 10)
        except ValueError:
            raise PublicKnowledgeFetchError(
                PublicKnowledgeFetchErrorCode.INVALID_RESPONSE
            ) from None
        if length < 0:
            raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.INVALID_RESPONSE)
        if length > max_response_bytes:
            raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.RESPONSE_TOO_LARGE)
    chunks: list[bytes] = []
    total = 0
    while chunk := response.read(READ_CHUNK_BYTES):
        total += len(chunk)
        if total > max_response_bytes:
            raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.RESPONSE_TOO_LARGE)
        chunks.append(chunk)
    return content_type, b"".join(chunks)


def _peer_address(connection: _PinnedHTTPSConnection) -> IPAddress:
    if connection.sock is None:
        raise PublicKnowledgeFetchError(
            PublicKnowledgeFetchErrorCode.NETWORK_FAILURE, retryable=True
        )
    try:
        return ipaddress.ip_address(connection.sock.getpeername()[0])
    except (OSError, ValueError, IndexError):
        raise PublicKnowledgeFetchError(
            PublicKnowledgeFetchErrorCode.NETWORK_FAILURE, retryable=True
        ) from None


def _perform_request(
    parsed: SplitResult, host: str, address: IPAddress, policy: PublicKnowledgeFetchPolicy
) -> tuple[int, str | None, str | None, bytes | None]:
    connection = _new_connection(host, str(address), policy.timeout_seconds)
    try:
        connection.connect()
        peer = _peer_address(connection)
        if peer != address or not _is_allowed_address(peer):
            raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.PEER_MISMATCH)
        connection.request(
            "GET",
            _request_target(parsed),
            headers={
                "Accept": ", ".join(sorted(ALLOWED_CONTENT_TYPES)),
                "Accept-Encoding": "identity",
                "Connection": "close",
                "User-Agent": USER_AGENT,
            },
        )
        response = connection.getresponse()
        if response.status in REDIRECT_STATUSES:
            return response.status, response.getheader("Location"), None, None
        if not 200 <= response.status <= 299:
            retryable = response.status in RETRYABLE_HTTP_STATUSES or response.status >= 500
            raise PublicKnowledgeFetchError(
                PublicKnowledgeFetchErrorCode.HTTP_STATUS, retryable=retryable
            )
        content_type, body = _read_success_body(response, policy.max_response_bytes)
        return response.status, None, content_type, body
    except PublicKnowledgeFetchError:
        raise
    except TimeoutError:
        raise PublicKnowledgeFetchError(
            PublicKnowledgeFetchErrorCode.TIMEOUT, retryable=True
        ) from None
    except ssl.SSLError:
        raise PublicKnowledgeFetchError(
            PublicKnowledgeFetchErrorCode.TLS_FAILURE, retryable=True
        ) from None
    except (OSError, http.client.HTTPException):
        raise PublicKnowledgeFetchError(
            PublicKnowledgeFetchErrorCode.NETWORK_FAILURE, retryable=True
        ) from None
    finally:
        connection.close()


def fetch_public_knowledge(
    url: str, policy: PublicKnowledgeFetchPolicy
) -> PublicKnowledgeFetchResult:
    """Fetch one explicitly approved public knowledge URL through a fail-closed boundary."""

    current_url = url
    redirects = 0
    while True:
        parsed, host = _validate_url(current_url, policy)
        address = _resolve_host(host)[0]
        status, location, content_type, body = _perform_request(parsed, host, address, policy)
        if status in REDIRECT_STATUSES:
            if location is None or not location.strip():
                raise PublicKnowledgeFetchError(
                    PublicKnowledgeFetchErrorCode.REDIRECT_MISSING_LOCATION
                )
            if redirects >= MAX_REDIRECTS:
                raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.TOO_MANY_REDIRECTS)
            current_url = urljoin(current_url, location.strip())
            redirects += 1
            continue
        if content_type is None or body is None:
            raise PublicKnowledgeFetchError(PublicKnowledgeFetchErrorCode.INVALID_RESPONSE)
        return PublicKnowledgeFetchResult(current_url, status, content_type, body)
