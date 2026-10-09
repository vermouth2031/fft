"""Install the accepted Phase 10 UDP boot image using the existing SD transaction.

Explicit --write is required. Retains the old BOOT.BIN under a unique name,
verifies full readback, then performs an SD-mode system reset. A physical power
cycle is separate and must be confirmed by the user, never inferred here.
"""
import argparse
import json
import secrets
import shutil
import struct
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/maintenance'), str(ROOT / 'host')]
import sd_boot_update as maintenance
from verify_phase10_evidence import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--board', default='192.168.1.10')
    args = parser.parse_args()
    require, sha, save = maintenance.require, maintenance.sha, maintenance.save
    require(args.write, 'Explicit --write is required')
    plan = maintenance.load_plan(SimpleNamespace(plan=args.plan), require_built=True)
    accepted = verify(ROOT)
    require(all(accepted['artifacts'][n] == h for n, h in plan['artifacts'].items()),
            'SD plan differs from the exact RAM/JTAG accepted artifacts')
    out = args.out.resolve()
    require(out.is_relative_to(ROOT / 'reports') and not out.exists(), 'Use a new reports directory')
    out.mkdir(parents=True)
    image = ROOT / 'artifacts/BOOT_udp.BIN'
    blob = image.read_bytes()
    require(0 < len(blob) <= maintenance.IMAGE_LIMIT, 'Invalid image size')
    nonce = secrets.randbits(28)
    crc = zlib.crc32(blob)
    control = out / 'control.bin'
    control.write_bytes(struct.pack('<16I', 0x53444231, 0x57524954, len(blob), crc, nonce, *([0] * 11)))
    shutil.copyfile(args.plan, out / 'maintenance_plan.json')
    report = dict(status='RUNNING', started_at=maintenance.now(), board=args.board,
        build_id=accepted['build_id'], hardware=accepted['hardware'],
        power_supply='USER_CONFIRMED_USB_ONLY', artifacts=plan['artifacts'],
        image_sha256=sha(image), image_bytes=len(blob), image_crc32=f'{crc:08x}',
        original_boot_backup=f'B{nonce:07X}.BIN', temporary=f'N{nonce:07X}.BIN',
        acceptance_sha256=sha(ROOT / 'reports/phase10_acceptance.json'),
        maintenance_elf_sha256=plan['elf_sha256'], sd_write_verified=False,
        boot_medium_verified=False, physical_cold_boot='NOT_PERFORMED',
        sources={str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in (
            Path(__file__), maintenance.HERE / 'sd_boot_writer.c',
            maintenance.HERE / 'sd_boot_writer.tcl', maintenance.HERE / 'sd_boot_reset.tcl')})
    save(out / 'installation.json', report)
    try:
        info = maintenance.stop_capture(args.board)
        require(info == accepted['hardware'], 'Live board differs from accepted configuration')
        # Read boot straps without resetting or programming anything.
        probe = out / 'read_boot_mode.tcl'
        probe.write_text('connect\ntargets -set -filter {name =~ "ARM*#0"}\n'
            'set mode [expr {[lindex [mrd -value 0xf800025c 1] 0] & 7}]\n'
            'puts "BOOT_MODE=$mode"\n'
            'if {$mode != 5} {error "SD boot mode required"}\ndisconnect\n')
        output = maintenance.run_logged([plan['xsdb'], probe], out / 'boot_mode.log', 30)
        require('BOOT_MODE=5' in output, 'SD boot mode not confirmed; no SD write performed')
        report['boot_mode'] = 5
        save(out / 'installation.json', report)
        output = maintenance.run_logged([plan['xsdb'], maintenance.HERE / 'sd_boot_writer.tcl',
            plan['elf'], image, ROOT / 'artifacts/ps7_init.tcl', control, out, 'WRITE_BOOT_BIN'],
            out / 'write.log', 360)
        require('SD_BOOT_READBACK_EXPORTED' in output, 'Writer did not export readback')
        values = struct.unpack('<16I', (out / 'mailbox.bin').read_bytes())
        report['mailbox_words'] = list(values)
        require(values[:5] == (0x53444231, 0x57524954, len(blob), crc, nonce), 'Mailbox input mismatch')
        require(values[5:10] == (2, 15, 0, len(blob), len(blob)), 'Incomplete write/readback')
        require(values[10:] == (crc, crc, 0xffffffff, 1, 1, 0), 'CRC/backup/install/rollback failed')
        readback = out / 'sd_boot_readback.bin'
        require(readback.stat().st_size == len(blob) and sha(readback) == sha(image),
                'Readback differs; do not reset')
        require(plan['artifacts'] == maintenance.current_artifacts(), 'Artifacts changed during installation')
        report.update(status='SD_WRITE_VERIFIED', sd_write_verified=True, readback_sha256=sha(readback))
        save(out / 'installation.json', report)
        output = maintenance.run_logged([plan['xsdb'], maintenance.HERE / 'sd_boot_reset.tcl',
            'BOOT_FROM_SD'], out / 'reset.log', 30)
        require('SD_SYSTEM_RESET_REQUESTED boot_mode=5' in output, 'SD reset not confirmed')
        report['reboot_hardware'] = maintenance.check_restarted(args.board, info)
        report.update(status='SD_INSTALL_AND_SYSTEM_RESET_PASS', boot_medium_verified=True,
            boot_verification_scope='SD-mode system reset and network identity; physical power cycle is separate')
        print('PHASE10_SD_INSTALL_AND_SYSTEM_RESET_PASS', accepted['build_id'], flush=True)
    except Exception as error:
        report.update(status='FAIL', error=str(error),
            recovery='Preserve named B/N files. If a writer timed out, inspect mailbox before any reset; CPU may still be writing.')
        raise
    finally:
        report['finished_at'] = maintenance.now()
        report['files'] = {p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*')
                           if p.is_file() and p.name != 'installation.json'}
        save(out / 'installation.json', report)


if __name__ == '__main__':
    main()
