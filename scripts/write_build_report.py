"""Write a current build-only report; board evidence is deliberately separate."""
from pathlib import Path
import datetime
import json
import re
from record_build_stage import verify

ROOT = Path(__file__).resolve().parents[1]


def main():
    verify("simulation")
    verify("hardware")
    read = lambda name: json.loads((ROOT / "reports" / name).read_text(encoding="utf-8"))
    hardware = read("hardware_validation.json")
    core = read("core_validation.json")
    software = read("software_validation.json")
    lines = ["# 当前构建验证报告", "",
             f"生成时间：{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}。",
             "", "本报告证明RTL仿真、布局布线和软件构建；实际板测状态见 docs/验收状态.md 及对应的实板证据。",
             "不会从历史板测报告推断当前代码已上板，也不猜测用户是否连接了开发板。", "",
             "| 项目 | 本次构建结果 |", "|---|---|",
             f"| 核心数值回归 | {core['status']}；FFT点数 {core['exact_fft_points']} |",
             f"| 仿真最大分析延迟 | {core['maximum_analysis_latency_us']} µs |",
             f"| setup / hold | {hardware['setup_slack_ns']} / {hardware['hold_slack_ns']} ns |",
             f"| CDC Critical / 未约束内部端点 | {hardware['cdc_critical']} / {hardware['unconstrained_internal_endpoints']} |",
             f"| 软件构建 | {software['status']} |",
             f"| XSA SHA-256 | {software['xsa_sha256']} |", "",
             "配置：I/Q各16位、100MSPS源、125MHz FFT核、8192点AMD FFT。",
             "新增帧长及频谱边界测试的具体结果见 build/logs 下的对应PASS日志。", "",
             "来源：simulation_provenance.json、hardware_provenance.json、software_validation.json。",
             "发布前应重查来源散列；修改代码、约束或参考后不得直接沿用本报告。", "",
             "## 实现资源", "", "| 资源 | 使用 | 可用 | 使用率 |", "|---|---:|---:|---:|"]
    utilization = (ROOT / "reports/utilization_flat.rpt").read_text()
    for label in ("Slice LUTs", "Slice Registers", "Block RAM Tile", "DSPs"):
        match = re.search(r"\|\s*" + label + r"\s*\|\s*([\d.]+)\s*\|\s*0\s*\|\s*0\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)", utilization)
        if match:
            lines.append(f"| {label} | {' | '.join(match.groups())} |")
    (ROOT / "reports/构建验证报告.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("BUILD_REPORT_PASS")


if __name__ == "__main__":
    main()

