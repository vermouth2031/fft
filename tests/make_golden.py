"""Generate unchanged legacy golden data using the reusable AMD oracle."""
from pathlib import Path
import argparse
import json
import shutil
import numpy as np
from fft_reference import FFTReference, N
ROOT = Path(__file__).resolve().parents[1]


def generate(output=ROOT / 'data'):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    vectors = ROOT / 'data/vectors'
    manifest = json.loads((vectors / 'reference_manifest.json').read_text(encoding='utf-8'))
    shutil.copyfile(vectors / 'hann_u18_f17.mem', output / 'hann_u18_f17.mem')
    cases, out_fft, input_words = [], [], []
    with FFTReference() as reference:
        for mode in ('rect', 'hann'):
            for name, case in manifest['cases'].items():
                iq = np.fromfile(vectors / case['binary'], dtype='<i2').reshape(-1, 2).astype(np.int64)
                input_words.extend((iq[:, 0] & 65535) | ((iq[:, 1] & 65535) << 16))
                result = dict(name=name, mode=mode, windows=[], bursts=case['bursts'])
                for wid in range(4):
                    window, packed, _ = reference.window(iq[wid*N:(wid+1)*N], mode, wid)
                    result['windows'].append(window)
                    out_fft.extend(packed)
                cases.append(result)
    (output / 'golden_fft.mem').write_text(''.join(f'{int(w):012x}\n' for w in out_fft), encoding='ascii')
    (output / 'test_iq.mem').write_text(''.join(f'{int(w):08x}\n' for w in input_words), encoding='ascii')
    (output / 'golden_results.json').write_text(json.dumps({
        'oracle': 'AMD xfft v9.1 bit-accurate model from Vivado 2026.1', 'cases': cases}, indent=2), encoding='utf-8')
    assert cases[1]['windows'][0]['f_peak_hz'] == 25_000_000
    assert cases[2]['windows'][0]['f_peak_hz'] == -25_000_000
    print(f'Generated {len(cases)} cases, {len(out_fft)} exact complex FFT outputs.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'data')
    generate(parser.parse_args().out)
