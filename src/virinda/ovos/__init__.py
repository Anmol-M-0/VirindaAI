"""OpenVoiceOS integration adapters.

OVOS is an optional runtime dependency. The core Virinda package intentionally remains
usable without OVOS for tests, automation, and headless integrations.
"""

from virinda.ovos.bridge import OVOSBridgeError, OVOSMessageBusBridge

__all__ = ["OVOSMessageBusBridge", "OVOSBridgeError"]
