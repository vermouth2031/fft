"""Offline verification of a saved finite board capture against this IQ demo pack.

Usage:
    python verify_saved_capture.py "path/to/capture_directory"
    python verify_saved_capture.py "path/to/capture_directory" --reference "path/to/reference.json"

No board communication is performed. Existing capture files are read without
modification. The only output is showcase_validation.json in the capture folder.
The demo pack's finite references do not verify cyclic captures.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import sys
import traceback
from pathlib import Path
from portable import materialized_reference, discover_project

sys.dont_write_bytecode = True

PACK_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PACK_ROOT / "manifest.json"
REPORT_NAME = "showcase_validation.json"
CAPTURE_EVIDENCE = (
    "capture.json", "frequency.bin", "burst.bin", "snapshot.bin", "snapshot.json"
)


def now() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message: str):
    if not condition:
        raise ValueError(message)


def pack_path(relative) -> Path:
    """Resolve a manifest-owned file without escaping the demo directory."""
    require(isinstance(relative, str) and relative, "演示清单中的文件路径缺失。")
    path = (PACK_ROOT / relative).resolve()
    require(path.is_relative_to(PACK_ROOT), "演示清单路径超出了本演示包目录。")
    require(path.is_file(), f"演示包文件不存在：{path}")
    return path


def explicit_reference_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() and not path.is_file():
        path = PACK_ROOT / path
    path = path.resolve()
    require(path.is_file(), f"指定的参考文件不存在：{path}")
    return path


def evidence_hashes(folder: Path) -> dict:
    return {name: digest(folder / name)
            for name in CAPTURE_EVIDENCE if (folder / name).is_file()}


def load_project(manifest: dict):
    value = manifest.get("project")
    require(isinstance(value, str) and value, "manifest.json 未记录相对工程 project 路径。")
    project = (PACK_ROOT / value).resolve()
    require(project == discover_project(PACK_ROOT), "manifest.json project 未指向所属仓库根目录。")
    verifier = project / "scripts" / "verify_board_capture.py"
    require(verifier.is_file(), f"原工程验证脚本不存在：{verifier}")
    for subdirectory in ("scripts", "tests", "host"):
        require((project / subdirectory).is_dir(),
                f"原工程缺少所需目录：{project / subdirectory}")
    sys.path[:0] = [str(project / name) for name in ("scripts", "tests", "host")]
    spec = importlib.util.spec_from_file_location("showcase_project_verifier", verifier)
    require(spec is not None and spec.loader is not None, "无法加载原工程验证脚本。")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from iq_client import decode_record
    return project, verifier, module.verify, decode_record


def last_window_mode(folder: Path, decode_record) -> str:
    path = folder / "frequency.bin"
    require(path.is_file(), "缺少 frequency.bin；请选择完整采集目录。")
    size = path.stat().st_size
    require(size > 0 and size % 128 == 0, "frequency.bin 为空或包含截断的窗口记录。")
    with path.open("rb") as stream:
        stream.seek(-128, 2)
        record = decode_record(stream.read(128), "frequency")
    return record["window"]


def choose_reference(manifest: dict, metadata: dict, mode: str,
                     explicit: str | None):
    input_hash = metadata.get("vector_sha256")
    require(isinstance(input_hash, str) and re.fullmatch(r"[0-9a-fA-F]{64}", input_hash),
            "capture.json 缺少有效的 vector_sha256，无法绑定输入来源。")
    input_hash = input_hash.lower()
    detector = metadata.get("applied_detector")
    require(isinstance(detector, dict),
            "capture.json 缺少 applied_detector，无法核对实际门限与检测模式。")
    cases = manifest.get("cases")
    require(isinstance(cases, list), "manifest.json 缺少 cases 列表。")
    matches = [case for case in cases
               if isinstance(case, dict) and str(case.get("sha256", "")).lower() == input_hash]
    require(matches, "这份采集的输入 SHA-256 不属于本演示包，请核对选择的 IQ 文件。")
    case = matches[0]
    vector = pack_path(case.get("file"))
    require(digest(vector) == input_hash, "演示包中的 IQ 文件内容已变化，SHA-256 与采集记录不一致。")

    scenarios = case.get("scenarios", [])
    candidates = [scenario for scenario in scenarios if isinstance(scenario, dict)
                  and scenario.get("request", {}).get("window") == mode
                  and scenario.get("applied_detector") == detector]
    if explicit:
        reference_path = explicit_reference_path(explicit)
        selected = next((scenario for scenario in candidates
                         if pack_path(scenario.get("reference_file")) == reference_path), None)
    else:
        require(candidates,
                "没有找到匹配本次窗函数及实际检测参数的有限回放参考。"
                "请使用演示说明中的设置，或用 --reference 指定相应参考文件。")
        selected = candidates[0]
        reference_path = pack_path(selected.get("reference_file"))

    reference = read_json(reference_path)
    require(reference.get("schema") == "iq-qualification-reference-v1", "参考文件格式不支持。")
    require(reference.get("replay", "finite") == "finite", "本工具只使用有限回放参考。")
    require(reference.get("input_sha256") == input_hash, "参考文件绑定的输入 SHA-256 不匹配。")
    require(reference.get("mode") == mode, "参考窗函数与实际频域记录不匹配。")
    require(reference.get("detector") == detector, "参考检测参数与实际 applied_detector 不匹配。")
    return case, selected, vector, reference_path


def run(folder: Path, explicit: str | None, report: dict):
    require(folder.is_dir(), "请选择保存 capture.json、frequency.bin 等文件的采集目录。")
    metadata_path = folder / "capture.json"
    require(metadata_path.is_file(), "采集目录中没有 capture.json。")
    metadata = read_json(metadata_path)
    report["capture_cyclic"] = metadata.get("cyclic")
    require(metadata.get("cyclic") is not True,
            "本演示包保存的是有限回放参考，不支持对循环采集进行完整数值核验。"
            "本次未执行数值核验，也不会输出 PASS。请按说明取消循环，重新保存一次有限采集。")
    require(metadata.get("cyclic") is False,
            "capture.json 未明确记录 cyclic=false，无法确认这是有限回放采集。")
    require(MANIFEST.is_file(), f"找不到本演示包 manifest.json：{MANIFEST}")
    manifest = read_json(MANIFEST)
    report.update(manifest=str(MANIFEST), manifest_sha256=digest(MANIFEST))
    project, verifier_path, verify, decode_record = load_project(manifest)
    report.update(project=str(project), verification_script=str(verifier_path),
                  verification_script_sha256=digest(verifier_path))
    mode = last_window_mode(folder, decode_record)
    case, scenario, vector, reference = choose_reference(manifest, metadata, mode, explicit)
    report.update(case_id=case.get("id"),
                  scenario_label=scenario.get("label") if scenario else "explicit reference",
                  input_file=str(vector), input_sha256=digest(vector),
                  window=mode, applied_detector=metadata["applied_detector"],
                  reference_file=str(reference), reference_sha256=digest(reference))
    before = evidence_hashes(folder)
    report["original_capture_sha256"] = before
    report["validation_performed"] = True
    try:
        with materialized_reference(reference, project) as temporary_reference:
            result = verify(folder, vector=vector, qualification=temporary_reference)
    finally:
        after = evidence_hashes(folder)
        report["capture_files_unchanged"] = after == before
        require(after == before, "核验前后原始采集文件散列不一致。")
    report.update(status="PASS", verification=result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="保存的真实有限采集目录")
    parser.add_argument("--reference", help="可选：显式指定本次配置对应的参考 JSON")
    args = parser.parse_args()
    folder = args.capture.expanduser().resolve()
    report = dict(schema="iq-showcase-saved-capture-validation-v1", status="FAIL",
                  started_at=now(), capture_directory=str(folder),
                  scope="Offline numerical verification of a saved real finite board capture. No board communication.",
                  board_access=False, validation_performed=False)
    try:
        run(folder, args.reference, report)
    except Exception as error:
        report.update(status="FAIL", error_type=type(error).__name__, error=str(error),
                      traceback=traceback.format_exc())
    report["finished_at"] = now()
    output = folder / REPORT_NAME
    if folder.is_dir():
        try:
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
            report["report_file"] = str(output)
        except OSError as error:
            report.update(status="FAIL", report_write_error=str(error))
    else:
        report["report_write_error"] = "采集目录不存在，未写入报告。"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
