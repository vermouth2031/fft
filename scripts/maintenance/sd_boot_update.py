"""Prepare/build a RAM-only SD writer; an actual update requires write --write.

The only installed image is the current, provenance-checked BOOT_udp.BIN.
Current JTAG board acceptance must pass before writing. No existing deployment
or board-validation record is modified by this utility.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import secrets
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_PLAN = ROOT / "build/maintenance/sd_boot_writer/plan.json"
IMAGE_LIMIT = 16 * 1024 * 1024
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "host"))
from package_release import check as check_build
from package_validated import check_board
from record_boot_stage import verify_boot
from iq_client import Client, capture
from verify_board_capture import verify as verify_capture


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def current_artifacts():
    check_build()
    verify_boot()
    names = ("iq_analyzer.bit", "iq_analyzer.xsa", "iq_udp.elf", "zynq_fsbl.elf",
             "BOOT_udp.BIN", "ps7_init.tcl")
    return {name: sha(ROOT / "artifacts" / name) for name in names}


def discover():
    software = json.loads((ROOT / "reports/software_validation.json").read_text(encoding="utf-8"))
    workspace = Path(software["workspace"]).resolve()
    commands = json.loads((workspace / "iq_sd/compile_commands.json").read_text(encoding="utf-8"))
    match = re.match(r'^(?:"([^"\r\n]+)"|(.+?\.exe))\s', commands[0]["command"])
    require(match is not None, "Cannot discover GCC from current SD app compile command")
    compiler_location = Path(match.group(1) or match.group(2))
    gcc = compiler_location.resolve()
    require(gcc.is_file() and gcc.name.lower() == "arm-none-eabi-gcc.exe", "Unexpected/missing ARM GCC")
    # Vitis/gnu may be a Windows junction into the common installation tree.
    installation = next((p for p in compiler_location.parents if p.name.lower() == "vitis"), None)
    require(installation is not None, "Cannot locate Vitis from the current compiler")
    bsp = workspace / "iq_platform/export/iq_platform/sw/standalone_a9"
    for name in ("include/ff.h", "include/xparameters.h", "Xilinx.spec", "lib/libxilffs.a"):
        require((bsp / name).is_file(), f"Current BSP lacks {name}")
    config = (bsp / "include/xilffs_config.h").read_text(encoding="utf-8")
    require(not re.search(r"^\s*#define\s+FILE_SYSTEM_READ_ONLY\b", config, re.M), "BSP is read-only")
    require(not re.search(r"^\s*#define\s+FILE_SYSTEM_USE_MKFS\b", config, re.M), "Unexpected format-enabled BSP")
    return workspace, gcc, installation / "bin/xsdb.bat", bsp


def prepare(args):
    identities = current_artifacts()
    workspace, gcc, xsdb, bsp = discover()
    destination = args.plan.resolve()
    require(destination.is_relative_to(ROOT / "build"), "Preparation must stay inside build/")
    destination.parent.mkdir(parents=True, exist_ok=True)
    original = (workspace / "iq_sd/src/lscript.ld").read_text(encoding="utf-8")
    linker, changes = re.subn(
        r"(ps7_ddr_0_memory_0\s*:\s*ORIGIN\s*=\s*0x100000,\s*LENGTH\s*=\s*)0x[0-9a-fA-F]+",
        lambda m: m.group(1) + "0x00f00000", original)
    require(changes == 1, "Unexpected DDR layout: do not risk overlapping image/mailbox buffers")
    linker_path = destination.parent / "lscript.ld"
    linker_path.write_text(linker, encoding="utf-8")
    dependencies = [HERE / "sd_boot_writer.c", HERE / "sd_boot_writer.tcl", HERE / "sd_boot_reset.tcl",
                    Path(__file__).resolve(), linker_path, bsp / "Xilinx.spec"]
    dependencies += list((bsp / "include").glob("*.h"))
    dependencies += [bsp / "lib" / name for name in
                     ("libxilffs.a", "libxilstandalone.a", "libxiltimer.a", "libxil.a")]
    plan = dict(prepared_at=now(), status="PREPARED_NOT_BUILT", workspace=str(workspace),
                gcc=str(gcc), xsdb=str(xsdb), bsp=str(bsp), linker=str(linker_path),
                elf=str(destination.parent / "sd_boot_writer.elf"), artifacts=identities,
                dependencies={str(p): sha(p) for p in dependencies},
                addresses=dict(program_start="0x00100000", program_end_exclusive="0x01000000",
                               mailbox="0x0ff00000", image="0x10000000", readback="0x12000000"),
                maximum_image_bytes=IMAGE_LIMIT, sd_card_touched=False)
    save(destination, plan)
    print(f"SD_MAINTENANCE_PREPARED {destination}")


def load_plan(args, require_built=False):
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    require(plan["artifacts"] == current_artifacts(), "Artifacts changed: prepare and build again")
    for name, digest in plan["dependencies"].items():
        require(sha(Path(name)) == digest, f"Maintenance source/BSP changed: {name}; prepare again")
    if require_built:
        require(plan["status"] == "BUILT" and sha(Path(plan["elf"])) == plan["elf_sha256"],
                "Maintenance ELF is missing, changed or not built")
    return plan


def run_logged(command, log, timeout):
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run([str(x) for x in command], cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    require(result.returncode == 0, f"Command failed; inspect {log}")
    return log.read_text(encoding="utf-8", errors="replace")


def build(args):
    plan = load_plan(args)
    bsp, elf, gcc = Path(plan["bsp"]), Path(plan["elf"]), Path(plan["gcc"])
    command = [gcc, "-DSDT", "-mcpu=cortex-a9", "-mfpu=vfpv3", "-mfloat-abi=hard",
               "-O2", "-g", "-Wall", "-Wextra", "-Werror", f"-specs={bsp / 'Xilinx.spec'}",
               "-isystem", bsp / "include", "-L", bsp / "lib", HERE / "sd_boot_writer.c",
               "-Wl,-T," + plan["linker"], "-Wl,-Map," + str(elf.with_suffix(".map")),
               "-Wl,--start-group", "-lxilffs", "-lxilstandalone", "-lxiltimer", "-lxil", "-lgcc", "-lc",
               "-Wl,--end-group", "-o", elf]
    log = elf.parent / "build.log"
    run_logged(command, log, 120)
    headers_log = elf.parent / "elf_program_headers.txt"
    text = run_logged([gcc.with_name("arm-none-eabi-readelf.exe"), "--wide", "--program-headers", elf],
                      headers_log, 30)
    load_segments = 0
    for line in text.splitlines():
        fields = line.split()
        if fields and fields[0] == "LOAD":
            start, size = int(fields[2], 16), int(fields[5], 16)
            require(0x00100000 <= start and start + size <= 0x01000000,
                    "Maintenance ELF overlaps reserved mailbox/image memory")
            load_segments += 1
    require(load_segments > 0, "No loadable maintenance ELF segments")
    plan.update(status="BUILT", built_at=now(), elf_sha256=sha(elf), build_log_sha256=sha(log),
                elf_headers_sha256=sha(headers_log))
    save(args.plan, plan)
    print(f"SD_MAINTENANCE_BUILD_PASS {elf}")


def stop_capture(board):
    client = Client(board)
    try:
        info = client.hardware_info("digital-zero")
        if client.read(8)[0] & 7:
            client.control(2)
            deadline = time.monotonic() + 15
            while client.read(8)[0] & 7:
                require(time.monotonic() < deadline, "Capture did not stop; SD writer not started")
                time.sleep(.05)
        return info
    finally:
        client.close()


def check_restarted(board, expected):
    deadline = time.monotonic() + 45
    while True:
        client = Client(board)
        try:
            info = client.hardware_info("digital-zero")
            require(info == expected, "SD-boot hardware capabilities/version/rate do not match JTAG acceptance")
            require(client.read(8)[0] & 7 == 0, "SD-boot design is not idle")
            require(client.read(0x60)[0] == 0, "SD-boot design reports hardware errors")
            return info
        except (OSError, TimeoutError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.5)
        finally:
            client.close()


def write(args):
    require(args.write, "Actual SD changes require the write subcommand AND --write")
    plan = load_plan(args, require_built=True)
    board_evidence = check_board()
    require(board_evidence["board"] == args.board, "Requested board differs from the full JTAG acceptance target")
    image = ROOT / "artifacts/BOOT_udp.BIN"
    blob = image.read_bytes()
    require(0 < len(blob) <= IMAGE_LIMIT, "BOOT image exceeds reserved DDR buffer")
    out = (args.out or ROOT / "build/maintenance" / ("sd_update_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))).resolve()
    require(out.is_relative_to(ROOT / "build/maintenance"), "Update output must stay inside build/maintenance/")
    out.mkdir(parents=True, exist_ok=False)
    nonce = secrets.randbits(28)
    expected_crc = zlib.crc32(blob)
    control = out / "control.bin"
    control.write_bytes(struct.pack("<16I", 0x53444231, 0x57524954, len(blob), expected_crc, nonce, *([0] * 11)))
    report = dict(status="RUNNING", started_at=now(), board=args.board, mode="udp", image=str(image),
                  image_sha256=sha(image), image_bytes=len(blob), image_crc32=f"{expected_crc:08x}",
                  original_boot_backup=f"B{nonce:07X}.BIN", temporary=f"N{nonce:07X}.BIN",
                  artifacts=plan["artifacts"], maintenance_elf_sha256=plan["elf_sha256"],
                  jtag_board_validation_sha256=sha(ROOT / "reports/current_board_validation.json"),
                  original_jtag_deployment_sha256=sha(ROOT / "reports/current_deployment.json"),
                  sd_write_verified=False, boot_medium_verified=False, output=str(out))
    destination = ROOT / "reports/sd_boot_update.json"
    save(out / "result.json", report)
    save(destination, report)
    try:
        info = stop_capture(args.board)
        require(info == board_evidence["hardware"], "Current board differs from the accepted JTAG configuration")
        log = out / "xsdb_write.log"
        output = run_logged([plan["xsdb"], HERE / "sd_boot_writer.tcl", plan["elf"], image,
                             ROOT / "artifacts/ps7_init.tcl", control, out, "WRITE_BOOT_BIN"], log, 360)
        require("SD_BOOT_READBACK_EXPORTED" in output, "Maintenance did not finish/export readback")
        values = struct.unpack("<16I", (out / "mailbox.bin").read_bytes())
        report["mailbox"] = dict(zip(("magic", "request", "size", "expected_crc", "nonce", "status",
                                      "stage", "fatfs_error", "written", "read_bytes", "source_crc",
                                      "readback_crc", "first_mismatch", "backup_created", "installed", "rollback"), values))
        require(values[:5] == (0x53444231, 0x57524954, len(blob), expected_crc, nonce), "Mailbox command changed")
        require(values[5] == 2 and values[6] == 15 and values[7] == 0 and values[8] == values[9] == len(blob),
                "Maintenance did not verify the complete file")
        require(values[10] == values[11] == expected_crc and values[12:] == (0xffffffff, 1, 1, 0),
                "Maintenance CRC, backup, install or rollback status invalid")
        readback = out / "sd_boot_readback.bin"
        require(readback.stat().st_size == len(blob) and sha(readback) == report["image_sha256"],
                "Host SHA-256 mismatch; do not reset the board or claim success")
        require(plan["artifacts"] == current_artifacts(), "Artifacts changed during the SD transaction")
        report.update(sd_write_verified=True, readback_sha256=sha(readback),
                      writer_log_sha256=sha(log), mailbox_sha256=sha(out / "mailbox.bin"))
        if args.reboot:
            reset_log = out / "xsdb_reset.log"
            output = run_logged([plan["xsdb"], HERE / "sd_boot_reset.tcl", "BOOT_FROM_SD"], reset_log, 30)
            require("SD_SYSTEM_RESET_REQUESTED boot_mode=5" in output, "No SD-mode reset evidence")
            report["reboot_hardware"] = check_restarted(args.board, info)
            capture_folder = ROOT / 'captures' / (out.name + '_sd_boot')
            require(not capture_folder.exists(), 'SD-reset capture destination already exists')
            capture(SimpleNamespace(board=args.board, port=5001,
                                    vector=str(ROOT / 'data/vectors/burst_fs4.bin'),
                                    out=str(capture_folder), window='hann', cyclic=False, seconds=1,
                                    detector='digital-zero', gap_min=32))
            measured = verify_capture(capture_folder)
            save(capture_folder / 'measurement_validation.json', measured)
            report.update(boot_medium_verified=True, reset_log_sha256=sha(reset_log),
                          post_boot_capture=measured,
                          boot_verification_scope='SD-mode system reset followed by exact finite numerical capture; not a physical power cycle')
        report.update(status="PASS", finished_at=now())
    except Exception as error:
        report.update(status="FAIL", error=str(error), finished_at=now())
        mailbox = out / "mailbox.bin"
        if mailbox.is_file() and mailbox.stat().st_size == 64:
            report["mailbox_words"] = list(struct.unpack("<16I", mailbox.read_bytes()))
        report["recovery"] = ("Do not delete/overwrite any generated Nxxxxxxx.BIN or Bxxxxxxx.BIN. "
                              "Inspect mailbox rollback status; original boot is retained at the named backup after successful install. "
                              "On timeout, CPU may still be writing; inspect before reset.")
        raise
    finally:
        save(out / "result.json", report)
        save(destination, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "build", "write"):
        command = sub.add_parser(name)
        command.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
        if name == "write":
            command.add_argument("--write", action="store_true", help="Explicitly authorize replacing SD root BOOT.BIN")
            command.add_argument("--reboot", action="store_true", help="After SHA-256 verification, reset in SD mode and verify UDP identity")
            command.add_argument("--board", default="192.168.1.10")
            command.add_argument("--out", type=Path)
    args = parser.parse_args()
    {"prepare": prepare, "build": build, "write": write}[args.command](args)


if __name__ == "__main__":
    main()
