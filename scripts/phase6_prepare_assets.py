"""Prepare build-bound Phase 6 robust and 125 MSPS OFDM references."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'host'), str(ROOT / 'scripts')]

from fft_reference import FS, N, digest
from generate_qualification_vectors import generate
from make_phase2_specs import case, qpsk
from phase4_ofdm import make_case
from phase4_prepare_bandwidth import prepare as prepare_ofdm
from phase4_prepare_widest import spec as widest_case
from threshold_config import PROFILES
from validate_measurements import prepare as prepare_measurements


def robust_reference(out):
    profile = PROFILES['robust']
    if profile != dict(on_multiple=3, off_multiple=1.75, kon=16, koff=8):
        raise ValueError('Selected robust detector profile changed')
    frames = [[2048 + i * 8192, 6144 + i * 8192] for i in range(4)]
    value = case('robust_snr5_120000', qpsk(4096), intervals=frames, seed=120000,
                 category='noise-validation', windows=['hann'], snr=5,
                 policy='quiet-prefix', group='robust_snr5')
    value['detector'].update(kon=16, koff=8)
    value['threshold_policy'].update(on_multiple=3, off_multiple=1.75)
    spec = out / 'robust_spec.json'
    spec.write_text(json.dumps({'schema': 'iq-qualification-spec-v1', 'cases': [value]}, indent=2) + '\n')
    manifest = generate(spec, out / 'robust_vectors')
    return prepare_measurements(manifest, out / 'robust_refs')


def ofdm_references(out):
    training = out / 'ofdm_training.json'
    training.write_text(json.dumps({
        'status': 'FROZEN',
        'sample_rate_hz': FS,
        'rule': 'Reuse the frozen Phase 4 widest waveform definition and gain; scale only the physical frequency axis.',
        'gain': 6000,
        'source_sha256': digest(ROOT / 'scripts/phase4_prepare_widest.py')
    }, indent=2) + '\n')
    finite = [widest_case(seed, modulation, 6000)
              for modulation in ('qpsk', 'qam16') for seed in range(212100, 212120)]
    prepare_ofdm(finite, out / 'ofdm_finite', training)

    # Exercise both frequency signs without wrapping, then explicit near-Nyquist wrapping cases.
    signed = [make_case(85, modulation, seed, gain=6000, carrier_hz=shift, windows=('rect', 'hann'), boundary=True)
              for modulation in ('qpsk', 'qam16') for seed in range(212120, 212123)
              for shift in (-4000000, -2000000, 0, 2000000, 4000000)]
    prepare_ofdm(signed, out / 'ofdm_signed', training)
    nyquist = [widest_case(212123, modulation, 6000, windows=('hann',))
               for modulation in ('qpsk', 'qam16')]
    for case_value, shift in zip(nyquist, (-2000000, 2000000)):
        case_value['signal']['carrier_hz'] = shift
        case_value['id'] += f'_f{shift}'
        case_value['crosses_nyquist'] = True
    prepare_ofdm(nyquist, out / 'ofdm_nyquist', training)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / 'build' / 'phase6'):
        parser.error('Output must be under build/phase6')
    out.mkdir(parents=True, exist_ok=False)
    robust = robust_reference(out)
    ofdm_references(out)
    result = {
        'status': 'PASS', 'sample_rate_hz': FS, 'fft_length': N,
        'robust_reference_index': str(robust),
        'generator_sha256': digest(Path(__file__))
    }
    (out / 'prepared.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PHASE6_ASSETS_READY', out, flush=True)


if __name__ == '__main__':
    main()
