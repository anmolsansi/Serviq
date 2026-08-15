"""Stable invitation domain failures."""


class InvitationError(RuntimeError):
    """Base invitation domain error."""


class InvitationAccessNotFoundError(InvitationError):
    error_code = "INVITATION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Invitation or organization was not found.")


class InvitationForbiddenError(InvitationError):
    error_code = "INVITATION_FORBIDDEN"

    def __init__(self) -> None:
        super().__init__("Invitation management is forbidden.")


class InvitationRoleInvalidError(InvitationError):
    error_code = "INVITATION_ROLE_INVALID"

    def __init__(self) -> None:
        super().__init__("One or more requested roles are not assignable.")


class InvitationConflictError(InvitationError):
    error_code = "INVITATION_CONFLICT"

    def __init__(self) -> None:
        super().__init__("Invitation conflicts with an existing pending invitation.")


class InvitationLifecycleConflictError(InvitationError):
    error_code = "INVITATION_LIFECYCLE_CONFLICT"

    def __init__(self) -> None:
        super().__init__("Invitation cannot be revoked from its current state.")
