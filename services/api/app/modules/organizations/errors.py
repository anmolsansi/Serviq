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


class OrganizationNotFoundError(OrganizationError):
    error_code = "ORGANIZATION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Organization was not found.")


class OrganizationSettingsForbiddenError(OrganizationError):
    error_code = "ORGANIZATION_SETTINGS_FORBIDDEN"

    def __init__(self) -> None:
        super().__init__("Organization settings access is forbidden.")
