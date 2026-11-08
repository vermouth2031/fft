"""Bind native replay RAM enables to this reproduction's final checkpoint."""
import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vivado-root', type=Path,
                        default=Path(os.environ.get('VIVADO_ROOT', r'D:\VivadoMM\2026.1\Vivado')))
    args = parser.parse_args()
    folder = ROOT / 'build/board/iq_board.runs/impl_1'
    checkpoint = folder / 'system_wrapper_postroute_physopt.dcp'
    if not checkpoint.is_file():
        checkpoint = folder / 'system_wrapper_routed.dcp'
    if not checkpoint.is_file():
        raise FileNotFoundError('A final routed checkpoint is required; run the Hardware stage first')
    hardware = json.loads((ROOT / 'reports/hardware_provenance.json').read_text(encoding='utf-8'))
    if hardware['artifacts']['artifacts/iq_analyzer.bit'] != sha(ROOT / 'artifacts/iq_analyzer.bit'):
        raise ValueError('Bitstream differs from the completed hardware-stage provenance')
    logs = ROOT / 'build/logs'
    logs.mkdir(parents=True, exist_ok=True)
    command = [str(args.vivado_root / 'bin/vivado.bat'), '-mode', 'batch', '-notrace', '-nojournal',
               '-log', str(logs / 'support_replay_enables.log'),
               '-source', str(ROOT / 'support/inspect_replay_enables.tcl'),
               '-tclargs', str(checkpoint)]
    with (logs / 'support_netlist_console.log').open('w', encoding='utf-8') as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
    table = ROOT / 'reports/phase13_replay_port_enables.tsv'
    rows = list(csv.DictReader(table.read_text(encoding='utf-8').splitlines(), delimiter='\t'))
    if len(rows) != 128 or len({row['cell'] for row in rows}) != 64:
        raise ValueError('Expected 64 replay RAM cells and 128 native enable pins')
    if any(row['driver_type'] in ('VCC', 'GND', '') for row in rows):
        raise ValueError('Replay RAM enable is constant or has no driver')
    for port in ('ENARDEN', 'ENBWREN'):
        if sum(row['port_enable'] == port for row in rows) != 64:
            raise ValueError(f'Expected 64 dynamic {port} enables')
    report = dict(status='BOTH_NATIVE_PORT_ENABLES_CONFIRMED',
                  created_at=datetime.datetime.now().astimezone().isoformat(),
                  build_id=json.loads((ROOT / 'build/config/build_identity.json').read_text(encoding='utf-8'))['build_id'],
                  replay_ramb36_count=64, dynamic_replay_enables=64, dynamic_host_enables=64,
                  constant_host_enables=0, checkpoint=checkpoint.relative_to(ROOT).as_posix(),
                  checkpoint_sha256=sha(checkpoint), table_sha256=sha(table),
                  scope='Fresh reproduction final routed netlist: 64 RAMB36 cells and 128 dynamic port enables; no power reduction or board-test claim.')
    (ROOT / 'reports/phase13_replay_enable_inspection.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('FRESH_NETLIST_NATIVE_ENABLES_PASS', flush=True)


if __name__ == '__main__':
    main()
