"""Verify the portable five-signal evidence archive without hardware or vendor tools."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'reports/five_signals_20260923'


def main():
    manifest = json.loads((ARCHIVE / 'report_integrity.json').read_text(encoding='utf-8'))
    if manifest['status'] != 'PASS':
        raise ValueError('Archive was not accepted')
    for name, expected in manifest['files'].items():
        path = (ARCHIVE / name).resolve()
        if not path.is_relative_to(ARCHIVE.resolve()) or not path.is_file():
            raise ValueError('Missing or invalid evidence path: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Evidence hash differs: ' + name)
    report = json.loads((ARCHIVE / 'validation.json').read_text(encoding='utf-8'))
    if report['status'] != 'PASS' or report['signal_groups'] != 5 or len(report['cases']) != 10:
        raise ValueError('Incomplete five-signal report')
    links = re.findall(r'\]\(([^)]+)\)', (ARCHIVE / '测试报告.md').read_text(encoding='utf-8'))
    for name in links:
        path = (ARCHIVE / name).resolve()
        if not path.is_relative_to(ARCHIVE.resolve()) or not path.is_file():
            raise ValueError('Broken report link: ' + name)
    print(f'FIVE_SIGNALS_ARCHIVE_PASS files={len(manifest["files"])} links={len(links)}')
    print('Checks preserved evidence and links; does not rerun FPGA tests.')


if __name__ == '__main__':
    main()
