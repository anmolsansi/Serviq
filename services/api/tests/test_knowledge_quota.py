from __future__ import annotations

from uuid import UUID

import pytest

from app.core.object_storage import knowledge_raw_key
from app.modules.knowledge.quota import parse_knowledge_raw_object_key

TENANT_ID = UUID("00000000-0000-0000-0000-000000000301")
SOURCE_ID = UUID("00000000-0000-0000-0000-000000000302")
OBJECT_ID = UUID("00000000-0000-0000-0000-000000000303")


def test_parse_knowledge_raw_object_key_accepts_only_canonical_trusted_identity() -> None:
    key = knowledge_raw_key(
        tenant_id=TENANT_ID,
        source_id=SOURCE_ID,
        object_id=OBJECT_ID,
    )
    parsed = parse_knowledge_raw_object_key(
        key.value,
        tenant_id=TENANT_ID,
        source_id=SOURCE_ID,
    )
    assert parsed == key


@pytest.mark.parametrize(
    "value,tenant_id,source_id",
    [
        ("arbitrary/path", TENANT_ID, SOURCE_ID),
        (
            f"tenants/{TENANT_ID}/knowledge/{SOURCE_ID}/raw/not-a-uuid",
            TENANT_ID,
            SOURCE_ID,
        ),
        (
            f"tenants/{UUID(int=999)}/knowledge/{SOURCE_ID}/raw/{OBJECT_ID}",
            TENANT_ID,
            SOURCE_ID,
        ),
        (
            f"tenants/{TENANT_ID}/knowledge/{UUID(int=998)}/raw/{OBJECT_ID}",
            TENANT_ID,
            SOURCE_ID,
        ),
    ],
)
def test_parse_knowledge_raw_object_key_rejects_untrusted_or_malformed_paths(
    value: str,
    tenant_id: UUID,
    source_id: UUID,
) -> None:
    with pytest.raises(ValueError):
        parse_knowledge_raw_object_key(value, tenant_id=tenant_id, source_id=source_id)
