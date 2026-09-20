"""Check the actual Vivado 2026.1 XCI against the declarative Tcl CONFIG values."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
XCI = ROOT / "build/vivado/iq_analyzer.srcs/sources_1/ip/fft8192/fft8192.xci"


def check():
    expected = dict(re.findall(r"CONFIG\.(\w+)\s+\{([^}]+)\}", (ROOT / "scripts/create_fft.tcl").read_text()))
    if not expected:
        raise ValueError("No FFT configuration found in create_fft.tcl")
    actual = json.loads(XCI.read_text(encoding="utf-8"))["ip_inst"]["parameters"]["component_parameters"]
    for name, value in expected.items():
        if name not in actual or actual[name][0]["value"].lower() != value.lower():
            raise ValueError(f"FFT XCI disagrees with create_fft.tcl: {name}; regenerate the FFT IP before building")
    return expected


if __name__ == "__main__":
    print("FFT_CONFIGURATION_PASS", len(check()))

