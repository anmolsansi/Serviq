"""Typed internal error boundary for API domain code.

HTTP mapping remains owned by a later global exception-handler ticket. Errors in this
module are safe, stable categories that internal services may raise without exposing
provider/library details.
"""


class AuthorizationContextError(RuntimeError):
    """Base class for trusted authentication/authorization-context failures."""

    error_code = "AUTHORIZATION_CONTEXT_INVALID"


class MissingTenantContextError(AuthorizationContextError):
    """Raised when tenant-scoped code is called without trusted tenant context."""

    error_code = "TENANT_CONTEXT_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Trusted tenant context is required.")
