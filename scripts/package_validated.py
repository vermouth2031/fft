"""Package current code only when build and matching real-board evidence pass."""
from __future__ import annotations
import argparse
import datetime
import json
import shutil
import zipfile
from pathlib import Path

from package_release import check, SD_VECTOR_NAMES
from record_build_stage import sha
from record_boot_stage import verify_boot

ROOT = Path(__file__).resolve().parents[1]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_board():
    report = json.loads((ROOT / "reports/current_board_validation.json").read_text(encoding="utf-8"))
    require(report["status"] == "PASS" and report["suite"] == "full", "Full current-board suite has not passed")
    require(report["hardware"]["hardware_version"] == 0x00010001, "Unexpected verified hardware version")
    require(sha(ROOT / 'reports/current_deployment.json') == report['deployment_sha256'], 'Deployment evidence changed')
    require(sha(Path(report['deployment']['log'])) == report['deployment']['log_sha256'], 'Deployment log changed')
    for name, value in report["artifacts"].items():
        require(sha(ROOT / "artifacts" / name) == value, f"Artifact differs from board-tested build: {name}")
    for files in report["source_files"].values():
        for name, value in files.items():
            require(sha(ROOT / name) == value, f"Source differs from board-tested code: {name}")
    for row in report["cases"]:
        require(row["status"] == "PASS", "Board numerical case failed")
        folder = Path(row["folder"])
        meta = json.loads((folder / 'capture.json').read_text(encoding='utf-8'))
        require(sha(Path(meta['vector'])) == row['input_sha256'], 'Board input vector changed')
        require(sha(folder / 'measurement_validation.json') == row['measurement_report_sha256'], 'Numerical report changed')
        for name, value in row["files"].items():
            require(sha(folder / name) == value, f"Board evidence changed: {folder / name}")
    return report


def supplementary_evidence():
    """Validate ancillary tests and return their exact project-local evidence."""
    board_hash = sha(ROOT / 'reports/current_board_validation.json')
    files = set()

    def checked(path, digest=None):
        path = Path(path).resolve()
        require(path.is_relative_to(ROOT), f'Evidence outside project: {path}')
        require(path.is_file(), f'Missing evidence: {path}')
        if digest is not None:
            require(sha(path) == digest, f'Changed evidence: {path}')
        files.add(path)

    for kind in ('extended', 'gui'):
        path = ROOT / 'reports' / f'current_{kind}_validation.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        require(report['status'] == 'PASS', f'{kind} validation did not pass')
        require(report['current_board_validation_sha256'] == board_hash, f'{kind} tests belong to another build')
        checked(path)
        folder = Path(report['folder'])
        checked(folder / f'{kind}_validation.json', sha(path))
        if kind == 'extended':
            checked(folder / 'host_clock_comparison.json')
            for row in report['cases']:
                for name, value in row['files'].items():
                    checked(Path(row['folder']) / name, value)
                checked(Path(row['metadata']['vector']), row['metadata']['vector_sha256'])
        else:
            for name, value in report['files'].items():
                checked(folder / name, value)
            for name, value in report.get('offline_files', {}).items():
                checked(Path(name), value)
    frame_path = ROOT / 'reports/frame_length_validation.json'
    frame = json.loads(frame_path.read_text(encoding='utf-8'))
    require(frame['status'] == 'PASS' and frame['board_report_sha256'] == board_hash,
            'Frame-boundary report does not match board acceptance')
    checked(frame_path)
    sd_test_path = ROOT / 'reports/current_sd_validation.json'
    sd_test = json.loads(sd_test_path.read_text(encoding='utf-8'))
    require(sd_test['status'] == 'PASS' and sd_test['system_resets_logged'] == 3,
            'Current SD application has not passed its independent 16-case suite')
    for name, value in sd_test['artifacts'].items():
        require(sha(ROOT / 'artifacts' / name) == value, f'SD-tested artifact changed: {name}')
    checked(sd_test_path)
    sd_folder = Path(sd_test['output'])
    checked(sd_folder / 'sd_validation.json', sha(sd_test_path))
    for name, value in sd_test['evidence_files'].items():
        checked(sd_folder / name, value)
    boot_verified = False
    sd_path = ROOT / 'reports/sd_boot_update.json'
    if sd_path.exists():
        sd = json.loads(sd_path.read_text(encoding='utf-8'))
        require(sd['status'] == 'PASS' and sd['sd_write_verified'], 'SD update is incomplete')
        require(sd['jtag_board_validation_sha256'] == board_hash, 'SD image belongs to another acceptance run')
        require(sd['image_sha256'] == sha(ROOT / 'artifacts/BOOT_udp.BIN'), 'SD image is stale')
        checked(sd_path)
        folder = Path(sd['output'])
        checked(folder / 'result.json', sha(sd_path))
        checked(folder / 'sd_boot_readback.bin', sd['readback_sha256'])
        checked(folder / 'xsdb_write.log', sd['writer_log_sha256'])
        checked(folder / 'mailbox.bin', sd['mailbox_sha256'])
        checked(folder / 'control.bin')
        boot_verified = sd['boot_medium_verified']
        if boot_verified:
            checked(folder / 'xsdb_reset.log', sd['reset_log_sha256'])
            capture = sd['post_boot_capture']
            require(capture['status'] == 'PASS', 'SD reset numerical test failed')
            for name, value in capture['files'].items():
                checked(Path(capture['folder']) / name, value)
            checked(Path(capture['folder']) / 'measurement_validation.json')
    return files, boot_verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check()
    verify_boot()
    for mode, artifact in (('sd_card', 'BOOT_sd.BIN'), ('ethernet_sd_card', 'BOOT_udp.BIN')):
        boot = ROOT / 'release' / mode / 'BOOT.BIN'
        require(boot.is_file() and sha(boot) == sha(ROOT / 'artifacts' / artifact),
                f'Stale or missing boot package: {mode}; rerun Package')
    for long_name, short_name in SD_VECTOR_NAMES.items():
        require(sha(ROOT / 'release/sd_card/VECTORS' / (short_name + '.BIN')) ==
                sha(ROOT / 'data/vectors' / (long_name + '.bin')), 'SD package vector is stale')
    board = check_board()
    extra_files, boot_verified = supplementary_evidence()
    if args.check:
        print("VALIDATED_PACKAGE_CHECK_PASS")
        return
    out = args.out or ROOT / "release" / ("validated_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    out = out.resolve()
    require(out.is_relative_to((ROOT / "release").resolve()), "Validated package must be inside release/")
    out.mkdir(parents=True, exist_ok=False)
    files = {}

    def add(source, relative=None):
        if not source.is_file() or "__pycache__" in source.parts:
            return
        relative = Path(relative or source.relative_to(ROOT))
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        value = sha(source)
        require(sha(destination) == value, f"Copy verification failed: {relative}")
        files[relative.as_posix()] = dict(bytes=source.stat().st_size, sha256=value)

    for folder in ("rtl", "constraints", "firmware", "host", "tests", "scripts", "docs", "vendor", "data", '.github'):
        for path in (ROOT / folder).rglob("*"):
            add(path)
    for name in ('iq_analyzer.bit', 'iq_analyzer.xsa', 'iq_udp.elf', 'iq_sd.elf',
                 'zynq_fsbl.elf', 'ps7_init.tcl', 'BOOT.BIN', 'BOOT_sd.BIN',
                 'BOOT_udp.BIN', 'boot_sd.bif', 'boot_udp.bif'):
        add(ROOT / 'artifacts' / name)
    for name in ("README.md", "CHANGELOG.md", "VERSION.json", "THIRD_PARTY_NOTICES.md",
                 "requirements.txt", "Open_IQ_Monitor.cmd", "Run_Network_Tests.cmd", '.gitattributes', '.gitignore'):
        add(ROOT / name)
    for mode in ("sd_card", "ethernet_sd_card"):
        for path in (ROOT / "release" / mode).rglob("*"):
            add(path, Path("boot_packages") / mode / path.relative_to(ROOT / "release" / mode))
    reports = ("core_validation.json", "hardware_validation.json", "software_validation.json",
               "simulation_provenance.json", "hardware_provenance.json", "boot_provenance.json", "current_board_validation.json", 'current_deployment.json',
               "timing_summary.rpt", "utilization_flat.rpt", "cdc.rpt", "drc.rpt", "worst_paths.rpt",
               "bus_skew.rpt", "构建验证报告.md", "本轮优化验收报告.md",
               "frame_length_validation.json", "帧长度定义与误差分析.md",
               "sd_boot_update.json", "current_gui_validation.json", "current_extended_validation.json",
               "current_sd_validation.json", "roi_timing.json", "roi_input_timing.rpt", "roi_peak_timing.rpt")
    for name in reports:
        path = ROOT / "reports" / name
        if path.exists():
            add(path)
    for stage in ('simulation', 'hardware'):
        provenance = json.loads((ROOT / 'reports' / (stage + '_provenance.json')).read_text(encoding='utf-8'))
        for name in set(provenance['evidence']) | set(provenance['inputs']):
            add(ROOT / name)
    deployment_log = Path(board['deployment']['log']).resolve()
    require(deployment_log.is_relative_to(ROOT), 'Deployment log outside project')
    add(deployment_log)
    add(ROOT / 'build/vivado/iq_analyzer.sim/sim_1/behav/xsim/core_results.txt')
    for path in sorted(extra_files):
        add(path)
    for path in (ROOT / 'reports/baseline_20260917').iterdir():
        add(path)
    for row in board["cases"]:
        folder = Path(row["folder"])
        require(folder.is_relative_to(ROOT / "captures"), "Board capture outside project")
        for path in folder.iterdir():
            if path.name in ("capture.json", "frequency.bin", "burst.bin", "snapshot.bin",
                              "snapshot.json", "measurement_validation.json"):
                add(path)
    start = out / "START_HERE.md"
    start.write_text(
        "# 已验证工程交付\n\n先阅读 README.md 和 docs/验收状态.md。\n\n"
        "本包源于当前完整仿真、静态时序、软件构建和双模式实板数值验收。\n"
        "100MSPS为电脑装载后板内回放速率；FFT使用AMD IP。\n"
        "boot_packages内两套启动文件每次选择一套，实体SD是否已更新见当前验收状态。\n"
        "实板采集以原始二进制和capture.json为依据；JSON/CSV数组可重新导出。\n\n"
        "在解压目录运行 python scripts/verify_delivery.py . 可重查所有交付文件SHA-256。\n"
        "历史采集报告保留实际采集时的本机绝对路径；包内同名captures相对目录保存原始证据。\n",
        encoding="utf-8")
    files["START_HERE.md"] = dict(bytes=start.stat().st_size, sha256=sha(start))
    manifest = dict(created_at=datetime.datetime.now().astimezone().isoformat(),
                    hardware_version="0x00010001", board_tested=True,
                    validation_scope=board["scope"], boot_medium_verified=boot_verified,
                    input=board["input"], metrology_calibrated=False,
                    baseline_tag="2023-09-17", files=files)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive = out.with_suffix(".zip")
    require(not archive.exists(), "Archive already exists")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for name in sorted(files):
            target.write(out / name, name)
        target.write(out / "manifest.json", "manifest.json")
    with zipfile.ZipFile(archive) as target:
        require(target.testzip() is None, "ZIP CRC verification failed")
    result = dict(status="PASS", directory=str(out), archive=str(archive),
                  sha256=sha(archive), file_count=len(files) + 1)
    (out.parent / (out.name + "_check.json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
