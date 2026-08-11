"""Shared integration failure categories."""


class SundayIntegrationError(RuntimeError):
    """Base failure raised by an external integration."""


class AuthenticationError(SundayIntegrationError):
    """Credentials are missing, invalid, or unauthorized."""


class PermanentIntegrationError(SundayIntegrationError):
    """The request cannot succeed without configuration changes."""


class TransientIntegrationError(SundayIntegrationError):
    """The request may succeed when repeated later."""


class ReconciliationError(SundayIntegrationError):
    """An external effect cannot yet be proven safe."""
