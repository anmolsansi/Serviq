"""Organization domain failures with stable public categories."""


class OrganizationError(RuntimeError):
    """Base organization domain error."""


class OrganizationSlugConflictError(OrganizationError):
    error_code = "ORGANIZATION_SLUG_CONFLICT"

    def __init__(self) -> None:
        super().__init__("Organization slug is already in use.")


class OwnerRoleUnavailableError(OrganizationError):
    error_code = "ORGANIZATION_OWNER_ROLE_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Organization owner role is unavailable.")
