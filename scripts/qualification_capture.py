"""Qualification reuses the production host configuration and readback path."""
from types import SimpleNamespace
import iq_client
from threshold_reference import validate_detector


def capture(args, detector):
    validate_detector(detector)
    configured=SimpleNamespace(**vars(args))
    configured.threshold_config=dict(detector)
    iq_client.capture(configured)
