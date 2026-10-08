"""Reject a running image whose declared identity differs from the checked build."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_identity(hardware, root=ROOT):
    # Validate the generated package and complete input digest before comparing
    # the compact runtime identifier. The ID identifies source, not bitstream SHA.
    subprocess.run([sys.executable, str(root / 'scripts/phase4_build_config.py'), '--check'],
                   cwd=root, check=True, stdout=subprocess.DEVNULL)
    identity = json.loads((root / 'build/config/build_identity.json').read_text())
    profile = identity['profile']
    expected = {key: profile[key] for key in
                ('hardware_version', 'sample_rate_hz', 'timestamp_clock_hz',
                 'fft_clock_hz', 'record_format_version', 'scan_lanes')}
    if 'fft_length' in profile:
        expected.update(fft_length=profile['fft_length'],replay_bank_samples=profile['replay_bank_samples'],
                        frequency_ring_records=profile['frequency_records'],snapshot_group=profile['fft_length']//1024)
    expected['hardware_capabilities'] = profile['capabilities']
    expected['build_id'] = identity['full_input_sha256'][:32]
    for key, value in expected.items():
        if hardware.get(key) != value:
            raise ValueError(f'Running image identity mismatch: {key}: '
                             f'{hardware.get(key)!r} != {value!r}')
    return expected
