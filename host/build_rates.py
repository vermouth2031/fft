"""Clock units of the selected build; physical support is gated by the builder."""
import json
from pathlib import Path

PROFILE_PATH=Path(__file__).resolve().parents[1]/'config/build_profile.json'
profile=json.loads(PROFILE_PATH.read_text())
for name in ('sample_rate_hz','timestamp_clock_hz','fft_clock_hz'):
    if type(profile[name]) is not int or not 0 < profile[name] < 2**31:
        raise ValueError('Invalid build clock: '+name)
SAMPLE_RATE_HZ=profile['sample_rate_hz']
TIMESTAMP_CLOCK_HZ=profile['timestamp_clock_hz']
FFT_CLOCK_HZ=profile['fft_clock_hz']
if SAMPLE_RATE_HZ!=TIMESTAMP_CLOCK_HZ:
    raise ValueError('Record format 1 currently requires equal source and timestamp clocks')
