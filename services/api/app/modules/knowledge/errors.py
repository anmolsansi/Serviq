"""Typed knowledge-source and quota domain errors."""


class KnowledgeSourceForbiddenError(RuntimeError):
    """Caller lacks the tenant capability required to manage knowledge sources."""


class KnowledgeSourceNotFoundError(RuntimeError):
    """Knowledge source is absent from the caller's tenant scope."""


class KnowledgeSourceDisabledError(RuntimeError):
    """Disabled knowledge sources cannot start a new sync."""


class KnowledgeSourceQuotaExceededError(RuntimeError):
    """Tenant has no remaining knowledge-source slots."""


class KnowledgeStorageQuotaExceededError(RuntimeError):
    """Tenant has no remaining raw knowledge-file byte capacity."""


class KnowledgeUploadConcurrencyLimitedError(RuntimeError):
    """Tenant already has the maximum number of active file uploads."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(retry_after_seconds, 1)
        super().__init__("Knowledge upload concurrency limit exceeded.")


class KnowledgeQuotaUnavailableError(RuntimeError):
    """Authoritative tenant quota usage cannot currently be established."""
