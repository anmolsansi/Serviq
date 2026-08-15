"""Stable tenant member-management domain failures."""


class MemberManagementError(RuntimeError):
    """Base member-management error."""


class MembershipAccessNotFoundError(MemberManagementError):
    error_code = "MEMBERSHIP_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Membership or organization was not found.")


class MembershipForbiddenError(MemberManagementError):
    error_code = "FORBIDDEN"

    def __init__(self) -> None:
        super().__init__("Member management is forbidden.")


class MembershipRoleInvalidError(MemberManagementError):
    error_code = "MEMBERSHIP_ROLE_INVALID"

    def __init__(self) -> None:
        super().__init__("One or more requested roles are not assignable.")


class LastActiveOwnerConflictError(MemberManagementError):
    error_code = "LAST_ACTIVE_OWNER"

    def __init__(self) -> None:
        super().__init__("The organization must retain at least one active owner.")
