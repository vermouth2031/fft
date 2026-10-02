"""Transactionally update only QPSK4/QPSK2 on the physical SD card."""
import argparse
import datetime
import json
import re
import secrets
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'host')]
from sd_boot_update import discover, run_logged, sha, require, current_artifacts

EXPECTED_OLD = {
    4: '0bb843e8e2c2647e5b86e9b5fcce87be6d14d7d1f69456edc5ef256f0f5f539e',
    2: '23a7e95bca6883344d64f940a04e0f94832530f3ee81ad132ba4a0e12cd75146'}
VECTORS = {4: ROOT / 'data/vectors/qpsk_sps4.bin', 2: ROOT / 'data/vectors/qpsk_sps2.bin'}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', required=True)
    parser.add_argument('--previous-export', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    require(out.is_relative_to(ROOT / 'build/maintenance') and not out.exists(), 'Use a new maintenance output')
    exported = json.loads(args.previous_export.read_text())
    for number in VECTORS:
        require(exported['files'][f'VECTORS/QPSK{number}.BIN']['sha256'] == EXPECTED_OLD[number],
                'Physical SD old vector differs from the approved baseline export')
    out.mkdir(parents=True)
    workspace, gcc, xsdb, bsp = discover()
    source = HERE / 'sd_phase6_vector_writer.c'
    tcl = HERE / 'sd_phase6_vector_writer.tcl'
    original = (workspace / 'iq_sd/src/lscript.ld').read_text()
    linker, count = re.subn(r'(ps7_ddr_0_memory_0\s*:\s*ORIGIN\s*=\s*0x100000,\s*LENGTH\s*=\s*)0x[0-9a-fA-F]+',
        lambda m: m.group(1) + '0x00f00000', original)
    require(count == 1, 'Unexpected linker layout')
    linker_path = out / 'lscript.ld';linker_path.write_text(linker)
    elf = out / 'sd_phase6_vector_writer.elf'
    command = [gcc, '-DSDT', '-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard', '-O2', '-g',
        '-Wall', '-Wextra', '-Werror', f'-specs={bsp / "Xilinx.spec"}', '-isystem', bsp / 'include',
        '-L', bsp / 'lib', source, '-Wl,-T,' + str(linker_path), '-Wl,--start-group', '-lxilffs',
        '-lxilstandalone', '-lxiltimer', '-lxil', '-lgcc', '-lc', '-Wl,--end-group', '-o', elf]
    run_logged(command, out / 'build.log', 120)
    report = {'status': 'RUNNING', 'started_at': datetime.datetime.now().astimezone().isoformat(),
        'scope': 'Only VECTORS/QPSK4.BIN and VECTORS/QPSK2.BIN; no format or deletion',
        'artifacts': current_artifacts(), 'previous_export': str(args.previous_export.resolve()),
        'previous_export_sha256': sha(args.previous_export), 'writer_elf_sha256': sha(elf), 'files': []}
    save(out / 'result.json', report)
    try:
        for number, vector in VECTORS.items():
            folder = out / f'qpsk{number}';folder.mkdir()
            blob = vector.read_bytes();nonce = secrets.randbits(24);crc = zlib.crc32(blob)
            control = folder / 'control.bin'
            control.write_bytes(struct.pack('<16I', 0x36564543, number, len(blob), crc, nonce, *([0]*11)))
            log = folder / 'xsdb.log'
            text = run_logged([xsdb, tcl, elf, vector, ROOT / 'artifacts/ps7_init.tcl', control,
                               folder, 'WRITE_PHASE6_VECTOR'], log, 360)
            require('SD_VECTOR_READBACK_EXPORTED' in text, 'No complete readback marker')
            values = struct.unpack('<16I', (folder / 'mailbox.bin').read_bytes())
            require(values[:5] == (0x36564543, number, len(blob), crc, nonce), 'Mailbox request changed')
            require(values[5] == 2 and values[6] == 15 and values[7] == 0 and values[8] == values[9] == len(blob),
                    'Complete vector write was not verified')
            require(values[10] == values[11] == crc and values[12:] == (0xffffffff,1,1,0),
                    'Vector CRC/install/rollback state invalid')
            readback = folder / 'vector_readback.bin'
            require(readback.read_bytes() == blob, 'Byte-for-byte vector readback mismatch')
            report['files'].append({'path': f'VECTORS/QPSK{number}.BIN', 'old_sha256': EXPECTED_OLD[number],
                'new_sha256': sha(vector), 'bytes': len(blob), 'crc32': f'{crc:08x}',
                'backup': f'VECTORS/B{number}{nonce:06X}.BAK', 'readback_sha256': sha(readback),
                'mailbox_sha256': sha(folder / 'mailbox.bin'), 'log_sha256': sha(log)})
            save(out / 'result.json', report)
        report.update(status='PASS', finished_at=datetime.datetime.now().astimezone().isoformat())
    except Exception as error:
        report.update(status='FAIL', error=str(error), finished_at=datetime.datetime.now().astimezone().isoformat())
        raise
    finally:
        save(out / 'result.json', report)
    print('PHASE6_SD_VECTOR_UPDATE_PASS', out)


if __name__ == '__main__':
    main()
