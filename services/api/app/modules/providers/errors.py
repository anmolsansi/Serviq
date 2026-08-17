"""Stable provider-management domain failures."""


class ProviderManagementError(RuntimeError):
    """Base provider-management error."""


class ProviderNotFoundError(ProviderManagementError):
    error_code = "PROVIDER_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Provider connection was not found.")


class ProviderForbiddenError(ProviderManagementError):
    error_code = "FORBIDDEN"

    def __init__(self) -> None:
        super().__init__("Provider management is forbidden.")


class ProviderConflictError(ProviderManagementError):
    error_code = "PROVIDER_CONFLICT"

    def __init__(self) -> None:
        super().__init__("Provider connection conflicts with existing tenant configuration.")


class ProviderReferencedError(ProviderManagementError):
    error_code = "PROVIDER_IN_USE"

    def __init__(self) -> None:
        super().__init__("Provider connection is still referenced by a model configuration.")


class ProviderSecretCleanupError(ProviderManagementError):
    error_code = "PROVIDER_SECRET_CLEANUP_FAILED"

    def __init__(self) -> None:
        super().__init__("Provider metadata changed but secret cleanup requires attention.")
