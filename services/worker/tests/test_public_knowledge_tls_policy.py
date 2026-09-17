import ssl

from app.core.public_knowledge_fetch import _PinnedHTTPSConnection


def test_pinned_https_connection_requires_tls_1_2_or_newer() -> None:
    connection = _PinnedHTTPSConnection("example.com", "93.184.216.34", 1.0)
    try:
        assert connection._tls_context.minimum_version >= ssl.TLSVersion.TLSv1_2
    finally:
        connection.close()
