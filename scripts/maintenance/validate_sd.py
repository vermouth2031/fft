"""Exercise current iq_sd.elf and export 16 real SD captures through JTAG.

--prepare and --build are offline. --out runs three explicitly logged system
resets and the actual SD application, which creates one fresh RUNxxxx folder.
Neither the read-only exporter nor this runner modifies BOOT.BIN or vectors.
"""
from __future__ import annotations
import argparse
import json
import re
import struct
import sys
import zlib
from pathlib import Path, PurePosixPath

from sd_boot_update import ROOT, HERE, discover, require, sha, now, save, run_logged
from package_release import check as check_build
from record_boot_stage import verify_boot
from analyze_sd import analyze

PLAN = ROOT / "build/maintenance/sd_export/plan.json"
VECTORS = dict(ZERO="zero", POS25="tone_pos_fs4", NEG25="tone_neg_fs4", BURST="burst_fs4",
               QPSK4="qpsk_sps4", QPSK2="qpsk_sps2", SHORT512="short512_boundary", FULLNEG="negative_fullscale_dc")


def identities():
    check_build()
    verify_boot()
    return {name: sha(ROOT / "artifacts" / name) for name in
            ("iq_analyzer.bit", "iq_analyzer.xsa", "iq_sd.elf", "ps7_init.tcl")}


def prepare():
    artifacts = identities()
    workspace, gcc, xsdb, bsp = discover()
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    compiled_source = workspace / "iq_sd/src/main.c"
    require(sha(compiled_source) == sha(ROOT / "firmware/sd_main.c"), "SD application source differs from current firmware")
    endings = [n for n, line in enumerate(compiled_source.read_text().splitlines(), 1)
               if re.search(r"for\s*\(\s*;\s*;\s*\)\s*usleep\s*\(1000000\)", line)]
    require(len(endings) == 1, "Cannot identify the post-close SD completion line; do not guess a wait time")
    linker, count = re.subn(
        r"(ps7_ddr_0_memory_0\s*:\s*ORIGIN\s*=\s*0x100000,\s*LENGTH\s*=\s*)0x[0-9a-fA-F]+",
        lambda m: m.group(1) + "0x00f00000", (workspace / "iq_sd/src/lscript.ld").read_text())
    require(count == 1, "Unexpected SD linker layout")
    linker_path = PLAN.parent / "lscript.ld"
    linker_path.write_text(linker, encoding="utf-8")
    dependencies = [HERE / name for name in ("sd_export.c", "sd_export.tcl", "run_sd_application.tcl",
                                            "validate_sd.py", "sd_boot_update.py")]
    dependencies += [compiled_source, linker_path, bsp / "Xilinx.spec"]
    dependencies += list((bsp / "include").glob("*.h"))
    dependencies += [bsp / "lib" / name for name in
                     ("libxilffs.a", "libxilstandalone.a", "libxiltimer.a", "libxil.a")]
    row = dict(status="PREPARED", prepared_at=now(), artifacts=artifacts,
               gcc=str(gcc), xsdb=str(xsdb), bsp=str(bsp), linker=str(linker_path),
               compiled_source=str(compiled_source), completion_line=endings[0],
               elf=str(PLAN.parent / "sd_export.elf"),
               dependencies={str(path): sha(path) for path in dependencies})
    save(PLAN, row)
    print(f"SD_VALIDATION_PREPARED {PLAN}")


def load_plan(built=False):
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    require(plan["artifacts"] == identities(), "SD artifacts changed: prepare/build again")
    for name, expected in plan["dependencies"].items():
        require(sha(name) == expected, f"Exporter/source/BSP changed: {name}")
    if built:
        require(plan["status"] == "BUILT" and sha(plan["elf"]) == plan["elf_sha256"], "Read-only exporter is not built/current")
    return plan


def build():
    plan = load_plan()
    gcc, bsp, elf = Path(plan["gcc"]), Path(plan["bsp"]), Path(plan["elf"])
    command = [gcc, "-DSDT", "-mcpu=cortex-a9", "-mfpu=vfpv3", "-mfloat-abi=hard", "-O2", "-g",
               "-Wall", "-Wextra", "-Werror", f"-specs={bsp / 'Xilinx.spec'}", "-isystem", bsp / "include",
               "-L", bsp / "lib", HERE / "sd_export.c", "-Wl,-T," + plan["linker"],
               "-Wl,-Map," + str(elf.with_suffix(".map")), "-Wl,--start-group", "-lxilffs",
               "-lxilstandalone", "-lxiltimer", "-lxil", "-lgcc", "-lc", "-Wl,--end-group", "-o", elf]
    log = PLAN.parent / "build.log"
    run_logged(command, log, 120)
    headers = PLAN.parent / "elf_program_headers.txt"
    text = run_logged([gcc.with_name("arm-none-eabi-readelf.exe"), "--wide", "--program-headers", elf], headers, 30)
    count = 0
    for line in text.splitlines():
        fields = line.split()
        if fields and fields[0] == "LOAD":
            start, size = int(fields[2], 16), int(fields[5], 16)
            require(0x00100000 <= start and start + size <= 0x01000000, "Exporter overlaps mailbox/output DDR")
            count += 1
    require(count > 0, "Exporter has no loadable sections")
    plan.update(status="BUILT", built_at=now(), elf_sha256=sha(elf), build_log_sha256=sha(log))
    save(PLAN, plan)
    print(f"SD_EXPORT_BUILD_PASS {elf}")


def unpack_archive(archive, destination):
    data = archive.read_bytes()
    require(len(data) >= 16, "Truncated SD archive header")
    magic, mode, count, total = struct.unpack_from("<4I", data)
    require(magic == 0x31584453 and mode in (1, 2) and total == len(data), "Invalid SD archive")
    position = 16
    names, runs, files = set(), set(), {}
    for unused in range(count):
        require(position + 112 <= len(data), "Truncated SD record header")
        raw_path, size, crc, flags, reserved = struct.unpack_from("<96s4I", data, position)
        name = raw_path.split(b"\0", 1)[0].decode("ascii")
        relative = PurePosixPath(name)
        require(name not in names and not relative.is_absolute() and ".." not in relative.parts and
                "\\" not in name and ":" not in name and reserved == 0, "Unsafe/duplicate SD archive path")
        names.add(name)
        position += 112
        require(position + size <= len(data), "Truncated SD file")
        payload = data[position:position + size]
        require(zlib.crc32(payload) == crc, f"SD export CRC mismatch: {name}")
        if flags == 1:
            require(re.fullmatch(r"RUN[0-9]{4}", name) is not None and size == 0, "Invalid RUN directory entry")
            runs.add(name)
        else:
            require(flags == 0 and (re.fullmatch(r"VECTORS/[A-Z0-9]+\.BIN", name) is not None or
                    re.fullmatch(r"RUN[0-9]{4}/C[0-9]{2}/(?:META\.JSON|FREQ\.BIN|BURST\.BIN|SNAP\.BIN)", name) is not None),
                    "Unexpected SD export file")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(payload)
            files[name] = dict(bytes=size, sha256=sha(target), crc32=f"{crc:08x}")
        position = (position + size + 3) & ~3
    require(position == len(data), "Trailing/missing archive bytes")
    return mode, runs, files


def export_sd(plan, mode, run_id, folder):
    folder.mkdir()
    control = folder / "control.bin"
    control.write_bytes(struct.pack("<16I", 0x53444531, mode, run_id, *([0] * 13)))
    log = folder / "xsdb.log"
    text = run_logged([plan["xsdb"], HERE / "sd_export.tcl", plan["elf"], ROOT / "artifacts/ps7_init.tcl",
                       control, folder], log, 240)
    require("SD_READ_ONLY_EXPORT_PASS" in text, "SD export did not complete")
    mailbox = struct.unpack("<16I", (folder / "mailbox.bin").read_bytes())
    require(mailbox[:3] == (0x53444531, mode, run_id) and mailbox[3:6] == (2, 5, 0), "SD exporter mailbox failed")
    archive = folder / "files.sdx"
    require(archive.stat().st_size == mailbox[6] and zlib.crc32(archive.read_bytes()) == mailbox[8],
            "Complete SD archive size/CRC does not match board memory")
    actual_mode, runs, files = unpack_archive(archive, folder / "raw")
    require(actual_mode == mode and mailbox[7] == len(runs) + len(files), "Archive record count mismatch")
    save(folder / "export_manifest.json", dict(mode=mode, runs=sorted(runs), files=files,
                                             archive_sha256=sha(archive), mailbox=list(mailbox), log_sha256=sha(log)))
    return runs, files


def verify_metadata_and_snapshots(run):
    import numpy as np
    golden = json.loads((ROOT / "data/golden_results.json").read_text())["cases"]
    fft = np.array([int(word, 16) for word in (ROOT / "data/golden_fft.mem").read_text().splitlines()],
                   dtype=np.int64).reshape(16, 4, 8192)
    snapshot_values = 0
    for c, expected in enumerate(golden):
        folder = run / f"C{c:02d}"
        meta = json.loads((folder / "META.JSON").read_text())
        require(meta["hardware_version"] == 0x00010001 and meta["sample_rate_hz"] == 100000000 and
                meta["detector_mode"] == "threshold" and meta["gap_min"] == 32 and meta["case"] == c and
                meta["window"] == expected["mode"], f"New SD firmware metadata mismatch: case {c}")
        require(meta["frequency_records"] == 4 and meta["burst_records"] == (folder / "BURST.BIN").stat().st_size // 64,
                f"SD metadata record counts mismatch: case {c}")
        require(0 < meta["hardware_max_latency_cycles"] <= 200000 and
                0 < meta["hardware_max_publish_latency_cycles"] <= 200000, f"SD deadline exceeded: case {c}")
        snapshot = folder / "SNAP.BIN"
        require(snapshot.is_file() == bool(meta["snapshot_valid"]), f"SD snapshot presence mismatch: case {c}")
        if snapshot.is_file():
            require(0 <= meta["snapshot_window"] < 4, "Invalid finite SD snapshot window")
            packed = fft[c, meta["snapshot_window"]]
            real = ((packed & 0xffffff) ^ 0x800000) - 0x800000
            imag = (((packed >> 24) & 0xffffff) ^ 0x800000) - 0x800000
            expected_power = np.fft.fftshift(real * real + imag * imag).reshape(1024, 8).max(axis=1)
            actual = np.frombuffer(snapshot.read_bytes(), dtype="<u8")
            require(np.array_equal(actual, expected_power), f"SD snapshot numerical mismatch: case {c}")
            snapshot_values += 1024
    return snapshot_values


def validate(out):
    plan = load_plan(built=True)
    out = out.resolve()
    require(out.is_relative_to(ROOT / "captures"), "SD validation output must be inside captures/")
    out.mkdir(parents=True, exist_ok=False)
    report = dict(status="RUNNING", started_at=now(), method="Actual iq_sd.elf via JTAG; read-only FatFs raw export",
                  artifacts=plan["artifacts"], helper_sha256=plan["elf_sha256"],
                  helper_sources={str(path.relative_to(ROOT)): sha(path) for path in HERE.glob("sd_export.*")},
                  output=str(out), boot_medium_written=False, boot_medium_verified=False,
                  expected_system_resets=3, numerical_scope="16 threshold cases / 64 frequency windows; all bursts and available snapshots")
    target = ROOT / "reports/current_sd_validation.json"
    save(out / "sd_validation.json", report)
    save(target, report)
    try:
        before, vector_files = export_sd(plan, 1, 0, out / "before")
        require(set(vector_files) == {f"VECTORS/{name}.BIN" for name in VECTORS}, "SD vector set mismatch")
        for short, name in VECTORS.items():
            require(vector_files[f"VECTORS/{short}.BIN"]["sha256"] == sha(ROOT / "data/vectors" / (name + ".bin")),
                    f"SD VECTORS/{short}.BIN differs from the current reference; no automatic write performed")
        report["runs_before"] = sorted(before)
        run_name = next((f"RUN{n:04d}" for n in range(10000) if f"RUN{n:04d}" not in before), None)
        require(run_name is not None, "SD has no free RUN0000..RUN9999 name")
        require(plan["artifacts"] == identities(), "Artifacts changed before actual SD application execution")
        app_log = out / "xsdb_sd_application.log"
        text = run_logged([plan["xsdb"], HERE / "run_sd_application.tcl", ROOT / "artifacts/iq_analyzer.bit",
                           ROOT / "artifacts/iq_sd.elf", ROOT / "artifacts/ps7_init.tcl",
                           plan["compiled_source"], str(plan["completion_line"])], app_log, 180)
        require("SD_APPLICATION_REACHED_COMPLETION_LINE" in text, "SD application did not reach post-close completion")
        after, raw_files = export_sd(plan, 2, int(run_name[3:]), out / "after")
        require(after - before == {run_name} and before <= after, "Expected exactly one new RUN directory")
        require(all(name.startswith(run_name + "/") for name in raw_files), "Export contains another run's data")
        run = out / "after/raw" / run_name
        snapshot_values = verify_metadata_and_snapshots(run)
        analyze(run, out / "decoded")
        numerical = json.loads((out / "decoded/board_validation.json").read_text(encoding="utf-8"))
        require(numerical["status"] == "PASS" and len(numerical["cases"]) == 16, "Full SD numerical comparison failed")
        require(plan["artifacts"] == identities(), "Artifacts changed during SD acceptance")
        report.update(status="PASS", finished_at=now(), run_name=run_name, runs_after=sorted(after),
                      raw_directory=str(run), raw_files=raw_files, sd_vectors=vector_files,
                      numerical=numerical, numerical_report_sha256=sha(out / "decoded/board_validation.json"),
                      exact_snapshot_values=snapshot_values,
                      maximum_analysis_us=max(row["maximum_latency_us"] for row in numerical["cases"]))
    except Exception as error:
        report.update(status="FAIL", error=str(error), finished_at=now())
        raise
    finally:
        logs = list(out.rglob("*.log"))
        report["system_resets_logged"] = sum(path.read_text(errors="replace").count("SD_VALIDATION_SYSTEM_RESET purpose=") for path in logs)
        report["evidence_files"] = {path.relative_to(out).as_posix(): sha(path) for path in out.rglob("*")
                                    if path.is_file() and path.name != "sd_validation.json"}
        save(out / "sd_validation.json", report)
        save(target, report)
    print(f"CURRENT_SD_VALIDATION_PASS {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--build", action="store_true")
    action.add_argument("--out", type=Path, help="Execute actual SD firmware and export raw captures into a NEW captures/ directory")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.build:
        build()
    else:
        validate(args.out)


if __name__ == "__main__":
    main()
