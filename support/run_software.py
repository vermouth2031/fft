"""Capture Vitis output directly in Python, preserving complete failure logs."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vitis-root', type=Path,
                        default=Path(os.environ.get('XILINX_VITIS', r'D:\VivadoMM\2026.1\Vitis')))
    args = parser.parse_args()
    log = ROOT / 'build/logs/build_software.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [str(args.vitis_root / 'bin/vitis.bat'), '-s', str(ROOT / 'support/vitis_compat.py')]
    environment = dict(os.environ, XILINX_VITIS=str(args.vitis_root),
                       PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    print(f'SUPPORT_SOFTWARE_START log={log}', flush=True)
    with log.open('wb') as output:
        result = subprocess.run(command, cwd=ROOT, env=environment,
                                stdout=output, stderr=subprocess.STDOUT, check=False)
    raw = log.read_bytes()
    # Escaped bytes retain any mixed startup diagnostics without concealing
    # a genuine traceback, missing success marker or nonzero exit code.
    text = raw.decode('utf-8', errors='backslashreplace')
    if result.returncode or 'SOFTWARE_BUILD_PASS' not in text or 'Traceback' in text:
        print(text[-24000:], flush=True)
        print(f'SUPPORT_SOFTWARE_FAIL exit_code={result.returncode}; full_log={log}', flush=True)
        return 1
    print('SUPPORT_SOFTWARE_PASS SOFTWARE_BUILD_PASS; full_log=' + str(log), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
