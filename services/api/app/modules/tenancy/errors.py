"""Fail-closed tenant membership authorization failures."""


class TenantMembershipAccessError(RuntimeError):
    """The user has no active membership in the requested trusted tenant."""

    error_code = "TENANT_MEMBERSHIP_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Active tenant membership is required.")
