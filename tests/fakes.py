"""Fakes of the ports, for tests that don't touch Windows."""

from polyglotic_desktop.ports.credentials import DeviceCredentials


class MemoryCredentialStore:
    """`CredentialStore` in memory."""

    def __init__(self, saved: DeviceCredentials | None = None) -> None:
        self.saved = saved
        self.kept_install_id = saved.install_id if saved else None

    def load(self) -> DeviceCredentials | None:
        return self.saved if self.saved and self.saved.device_token else None

    def install_id(self) -> str | None:
        return self.kept_install_id

    def save(self, credentials: DeviceCredentials) -> None:
        self.saved = credentials
        self.kept_install_id = credentials.install_id

    def forget(self) -> None:
        self.saved = None  # the install id stays (decision 0080)
