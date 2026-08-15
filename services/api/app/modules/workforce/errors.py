"""Typed workforce identity domain failures."""


class WorkforceIdentityError(RuntimeError):
    """Base class for trusted workforce identity persistence failures."""


class DisabledWorkforceUserError(WorkforceIdentityError):
    """A verified external identity maps to a disabled Serviq user."""

    error_code = "WORKFORCE_USER_DISABLED"

    def __init__(self) -> None:
        super().__init__("Workforce user is disabled.")


class WorkforceIdentityProfileError(WorkforceIdentityError):
    """The verified identity lacks fields required by the frozen users schema."""

    error_code = "WORKFORCE_IDENTITY_PROFILE_INVALID"

    def __init__(self) -> None:
        super().__init__("Verified workforce identity profile is incomplete.")
