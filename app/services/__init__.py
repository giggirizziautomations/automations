"""Business services for the Automations API."""

from .msal_device import DeviceCodeLoginError, DeviceCodeLoginService

__all__ = ["DeviceCodeLoginError", "DeviceCodeLoginService"]
