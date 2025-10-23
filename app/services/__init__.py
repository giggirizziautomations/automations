"""Business services for the Automations API."""

from .microsoft_auth import (
    MicrosoftAuthenticationError,
    MicrosoftAuthenticationService,
)
from .msal_device import DeviceCodeLoginError, DeviceCodeLoginService
from .msal_playwright import PlaywrightDeviceLoginAutomation

__all__ = [
    "DeviceCodeLoginError",
    "DeviceCodeLoginService",
    "MicrosoftAuthenticationError",
    "MicrosoftAuthenticationService",
    "PlaywrightDeviceLoginAutomation",
]
