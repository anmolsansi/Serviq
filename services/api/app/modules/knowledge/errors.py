"""Typed knowledge-source domain errors."""


class KnowledgeSourceForbiddenError(RuntimeError):
    """Caller lacks the tenant capability required to manage knowledge sources."""
