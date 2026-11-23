"""Values shared by the app and its open-beta account adapter."""

from dataclasses import dataclass

CODE_LENGTH = 6  # v1 wire format, six ASCII digits


class AccountError(Exception):
    """A machine-readable failure. Show only messages chosen by the app."""

    def __init__(
        self,
        code: str,
        retry_after: int | None = None,
        *,
        status: int | None = None,
        diagnostic: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after
        self.status = status
        self.diagnostic = diagnostic  # a fixed label set by the client


@dataclass(frozen=True, slots=True)
class Region:
    country: str = "XX"
    pipl_cross_border_required: bool = False

    @property
    def needs_consent(self) -> bool:
        return self.country == "CN" or self.pipl_cross_border_required
