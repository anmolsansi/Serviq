"""Dependency boundary for knowledge-source object storage."""

from app.core.config import load_settings
from app.core.object_storage import ObjectStorage, build_object_storage


def get_knowledge_object_storage() -> ObjectStorage:
    return build_object_storage(load_settings())
