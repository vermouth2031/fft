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
FFT_LENGTH=profile.get('fft_length',8192)
if FFT_LENGTH not in (8192,16384,32768):raise ValueError('Unsupported FFT length')
FFT_LOG2=FFT_LENGTH.bit_length()-1
FFT_SCALING=[3]+[2]*(FFT_LOG2//2-1)+([1] if FFT_LOG2%2 else [])
REPLAY_BANK_SAMPLES=profile.get('replay_bank_samples',32768)
FREQUENCY_RECORDS=profile.get('frequency_records',256)
if SAMPLE_RATE_HZ!=TIMESTAMP_CLOCK_HZ:
    raise ValueError('Record format 1 currently requires equal source and timestamp clocks')
