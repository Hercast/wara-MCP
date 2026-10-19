from __future__ import annotations

from ..config import Config
from .base import Bridge


def make_bridge(config: Config) -> Bridge:
    if config.bridge == "fake":
        from .fake import FakeBridge

        return FakeBridge()
    from .altium import AltiumBridge

    return AltiumBridge(config)
