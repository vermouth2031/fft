"""Use the proven UDP capture path with explicit qualification-only configuration.

The scoped client factory changes only CONFIG payload construction, checks every
written threshold before START and restores the standard host afterwards. This
entry point is intentionally single-controller/single-thread, like the board.
"""
from unittest.mock import patch
import iq_client
from threshold_reference import validate_detector


def capture(args, detector):
    validate_detector(detector)
    original=iq_client.Client

    class ConfiguredClient(original):
        def configure(self, config, mode='threshold', gap_min=32, hardware=None):
            payload=list(config)
            payload[5:13]=[detector['ton']&0xffffffff,detector['ton']>>32,
                detector['toff']&0xffffffff,detector['toff']>>32,detector['kon'],detector['koff'],
                detector['max_burst_samples'],0]
            super().configure(payload,mode,gap_min,hardware)
            actual=list(self.read(0x34,7))
            if actual!=payload[5:12]:
                raise RuntimeError('Qualification threshold CONFIG readback mismatch before START')
            if hardware is not None:
                hardware['applied_detector']=dict(detector)
                hardware['threshold_registers_before_start']=actual

    with patch.object(iq_client,'Client',ConfiguredClient):
        iq_client.capture(args)
