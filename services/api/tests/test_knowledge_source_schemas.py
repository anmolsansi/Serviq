import pytest
from pydantic import ValidationError

from app.modules.knowledge.schemas import KnowledgeSourceCreateRequest


def test_knowledge_source_request_trims_name_and_uri() -> None:
    request = KnowledgeSourceCreateRequest.model_validate(
        {
            "sourceType": "url",
            "name": "  Help Center  ",
            "sourceUri": "  https://docs.example.com/help?lang=en  ",
            "accessScope": "customer",
        }
    )

    assert request.name == "Help Center"
    assert request.source_uri == "https://docs.example.com/help?lang=en"


@pytest.mark.parametrize(
    "source_uri",
    [
        "http://example.com",
        "file:///etc/passwd",
        "ftp://example.com/source.xml",
        "data:text/plain,hello",
        "javascript:alert(1)",
        "https:///missing-host",
        "https://user:secret@example.com/docs",
        "https://user@example.com/docs",
        "https://example.com/docs#fragment",
        "https://example.com/docs#",
        "https://example.com:bad/docs",
        "https://example.com/white space",
    ],
)
def test_knowledge_source_request_rejects_unsafe_or_invalid_uri(source_uri: str) -> None:
    with pytest.raises(ValidationError):
        KnowledgeSourceCreateRequest.model_validate(
            {
                "sourceType": "url",
                "name": "Docs",
                "sourceUri": source_uri,
                "accessScope": "customer",
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sourceType", "pdf"),
        ("accessScope", "public"),
        ("name", "   "),
        ("name", "x" * 161),
    ],
)
def test_knowledge_source_request_rejects_invalid_metadata(field: str, value: str) -> None:
    payload = {
        "sourceType": "url",
        "name": "Docs",
        "sourceUri": "https://example.com/docs",
        "accessScope": "customer",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        KnowledgeSourceCreateRequest.model_validate(payload)


def test_knowledge_source_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        KnowledgeSourceCreateRequest.model_validate(
            {
                "sourceType": "sitemap",
                "name": "Docs sitemap",
                "sourceUri": "https://example.com/sitemap.xml",
                "accessScope": "internal",
                "crawlNow": True,
            }
        )
