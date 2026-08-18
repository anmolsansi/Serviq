"""Stable provider/model-management domain failures."""


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


class ProviderTestRateLimitedError(ProviderManagementError):
    error_code = "PROVIDER_TEST_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(retry_after_seconds, 1)
        super().__init__("Provider connectivity-test rate limit exceeded.")


class ProviderTestUnavailableError(ProviderManagementError):
    error_code = "PROVIDER_TEST_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Provider connectivity testing is temporarily unavailable.")


class ProviderTestStaleError(ProviderManagementError):
    error_code = "PROVIDER_TEST_STALE"

    def __init__(self) -> None:
        super().__init__("Provider credential changed while the connectivity test was running.")


class ModelConfigurationNotFoundError(ProviderManagementError):
    error_code = "MODEL_CONFIGURATION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Model configuration was not found.")


class ModelConfigurationAliasConflictError(ProviderManagementError):
    error_code = "MODEL_ALIAS_CONFLICT"

    def __init__(self) -> None:
        super().__init__("Model alias already exists for this tenant.")


class ModelConfigurationProviderIneligibleError(ProviderManagementError):
    error_code = "MODEL_PROVIDER_INELIGIBLE"

    def __init__(self) -> None:
        super().__init__("Model configuration requires an active provider connection.")


class ModelConfigurationReferencedError(ProviderManagementError):
    error_code = "MODEL_CONFIGURATION_IN_USE"

    def __init__(self) -> None:
        super().__init__("Model configuration is still referenced by production configuration.")
