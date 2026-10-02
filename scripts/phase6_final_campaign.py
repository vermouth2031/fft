"""Prepare and run the complete Phase 6 2020-case board campaign."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'host'), str(ROOT / 'scripts')]
from fft_reference import FS, digest
from generate_qualification_vectors import generate
from phase4_ofdm import make_case
from phase4_prepare_bandwidth import prepare as prepare_ofdm
from phase4_prepare_widest import spec as widest_case
from validate_measurements import prepare as prepare_measurements

REFS = ROOT / 'build/phase6/candidate_a2_125_125/final_matrix'
CAPTURES = ROOT / 'captures/phase6/candidate_a2_125_125_final_matrix'
REGRESSION = ('validation', 'noise_only', 'legacy_regression', 'robust_regression',
              'wide_continuous', 'sensitivity')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def run(command, log):
    print('PHASE6_STAGE_START', log.stem, flush=True)
    with log.open('x', encoding='utf-8') as stream:
        result = subprocess.run([sys.executable, '-X', 'utf8', *map(str, command)],
                                cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Stage failed; inspect {log}')
    print('PHASE6_STAGE_PASS', log.stem, flush=True)


def prepare():
    REFS.mkdir(parents=True, exist_ok=False)
    run(['scripts/phase3_prepare_release.py', '--out', REFS / 'regression'], REFS / 'regression_prepare.log')
    run(['scripts/phase4_prepare_bandwidth.py', '--out', REFS / 'ofdm'], REFS / 'ofdm_prepare.log')

    noise = read(ROOT / 'config/phase5_regression_noise_spec.json')
    for case in noise['cases']:
        case['sample_rate_hz'] = FS
    noise_spec = REFS / 'noise_spec.json'
    save(noise_spec, noise)
    manifest = generate(noise_spec, REFS / 'noise/vectors')
    prepare_measurements(manifest, REFS / 'noise/references')

    expected = {'validation': 625, 'noise_only': 256, 'legacy_regression': 431,
                'robust_regression': 212, 'wide_continuous': 17, 'sensitivity': 112,
                'ofdm_finite': 240, 'ofdm_boundary': 24, 'widest_finite': 80, 'noise': 9}
    actual = {}
    for stage in REGRESSION:
        actual[stage] = len(read(REFS / f'regression/{stage}/references/index.json')['cases'])
    actual['ofdm_finite'] = len(read(REFS / 'ofdm/finite/index.json')['cases'])
    actual['ofdm_boundary'] = len(read(REFS / 'ofdm/boundary/index.json')['cases'])
    actual['widest_finite'] = len(read(ROOT / 'build/phase6/candidate_a2_125_125/ofdm_finite/index.json')['cases'])
    actual['noise'] = len(read(REFS / 'noise/references/index.json')['cases'])
    if actual != expected:
        raise ValueError(f'Prepared matrix count differs: {actual}')
    save(REFS / 'prepared.json', {'status': 'PASS', 'sample_rate_hz': FS,
         'counts': actual, 'generator_sha256': digest(Path(__file__))})
    print('PHASE6_FINAL_REFERENCES_READY', sum(actual.values()), flush=True)


def require_finite(path, count, minimum_hz=None):
    report = read(path)
    if report['status'] != 'PASS' or len(report['cases']) != count or len(report['legacy_cases']) != 16:
        raise ValueError(f'Incomplete finite matrix: {path}')
    if minimum_hz is not None:
        for row in report['cases']:
            for window in row['bandwidth']['windows']:
                if window['region'] == 'internal' and (window['normal_records'] != window['records']
                        or window['bandwidth_min_hz'] < minimum_hz):
                    raise ValueError(f'Bandwidth promotion gate failed: {row["label"]}')
    return report


def make_continuous():
    require_finite(CAPTURES / 'ofdm_finite/measurement_validation.json', 240)
    training = REFS / 'ofdm/training.json'
    gain = read(training)['gain']
    cases = []
    for modulation in ('qpsk', 'qam16'):
        cases += [make_case(95, modulation, 211000, gain=gain, seconds=10),
                  make_case(95, modulation, 211000, gain=gain, seconds=60, windows=('hann',))]
    cases.append(make_case(95, 'qpsk', 211000, gain=gain, seconds=300, windows=('hann',)))
    prepare_ofdm(cases, REFS / 'ofdm/continuous', training)

    widest_report = ROOT / 'captures/phase6/candidate_a2_125_125_ofdm_finite/measurement_validation.json'
    require_finite(widest_report, 80, 115000000)
    widest_training = ROOT / 'build/phase6/candidate_a2_125_125/ofdm_training.json'
    cases = []
    for modulation in ('qpsk', 'qam16'):
        cases += [widest_case(212100, modulation, 6000, 10),
                  widest_case(212100, modulation, 6000, 60, ('hann',))]
    cases.append(widest_case(212100, 'qpsk', 6000, 300, ('hann',)))
    prepare_ofdm(cases, REFS / 'widest_continuous', widest_training)


def capture():
    if read(REFS / 'prepared.json')['status'] != 'PASS':
        raise ValueError('References are not prepared')
    CAPTURES.mkdir(parents=True, exist_ok=False)
    report = {'status': 'RUNNING', 'started_at': datetime.datetime.now().astimezone().isoformat(),
              'sample_rate_hz': FS, 'stages': []}
    campaign = CAPTURES / 'campaign.json'
    save(campaign, report)

    def stage(name, command, matrix=None, reused=False):
        if reused:
            row = {'stage': name, 'status': 'PASS', 'reused': True, 'matrix': str(matrix),
                   'matrix_sha256': digest(matrix)}
        else:
            log = CAPTURES / f'{name}.log'
            run(command, log)
            row = {'stage': name, 'status': 'PASS', 'log': str(log), 'log_sha256': digest(log)}
            if matrix:
                row.update(matrix=str(matrix), matrix_sha256=digest(matrix))
        report['stages'].append(row)
        save(campaign, report)

    try:
        for name in REGRESSION:
            out = CAPTURES / name
            stage(name, ['scripts/validate_measurements.py', 'capture', '--references',
                  REFS / f'regression/{name}/references/index.json', '--out', out],
                  out / 'measurement_validation.json')
        for name in ('ofdm_finite', 'ofdm_boundary'):
            source = 'finite' if name.endswith('finite') else 'boundary'
            out = CAPTURES / name
            stage(name, ['scripts/phase4_validate_bandwidth.py', 'capture', '--references',
                  REFS / f'ofdm/{source}/index.json', '--out', out], out / 'measurement_validation.json')

        make_continuous()
        out = CAPTURES / 'ofdm_continuous'
        stage('ofdm_continuous', ['scripts/phase4_validate_bandwidth.py', 'capture', '--references',
              REFS / 'ofdm/continuous/index.json', '--out', out], out / 'measurement_validation.json')

        widest = ROOT / 'captures/phase6/candidate_a2_125_125_ofdm_finite/measurement_validation.json'
        stage('widest_finite', [], widest, reused=True)
        out = CAPTURES / 'widest_continuous'
        stage('widest_continuous', ['scripts/phase4_validate_bandwidth.py', 'capture', '--references',
              REFS / 'widest_continuous/index.json', '--out', out,
              '--minimum-bandwidth-hz', '115000000'], out / 'measurement_validation.json')

        out = CAPTURES / 'noise'
        stage('noise', ['scripts/validate_measurements.py', 'capture', '--references',
              REFS / 'noise/references/index.json', '--out', out], out / 'measurement_validation.json')
        report['status'] = 'PASS'
    except Exception as error:
        report.update(status='FAIL', error=str(error))
        raise
    finally:
        report['finished_at'] = datetime.datetime.now().astimezone().isoformat()
        save(campaign, report)
    print('PHASE6_FINAL_MATRIX_PASS', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'capture'))
    args = parser.parse_args()
    {'prepare': prepare, 'capture': capture}[args.action]()
