"""Check the actual Vivado 2026.1 XCI against the declarative Tcl CONFIG values."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
XCI = ROOT / "build/vivado16k/iq_analyzer.srcs/sources_1/ip/fft8192/fft8192.xci"


def check():
    expected = dict(re.findall(r"CONFIG\.(\w+)\s+\{([^}]+)\}", (ROOT / "scripts/create_fft.tcl").read_text()))
    if not expected:
        raise ValueError("No FFT configuration found in create_fft.tcl")
    profile=json.loads((ROOT/'config/build_profile.json').read_text())
    expected['target_clock_frequency']=f"{profile['fft_clock_hz']/1e6:g}"
    expected['target_data_throughput']=f"{profile['sample_rate_hz']/1e6:g}"
    expected['transform_length']=str(profile.get('fft_length',8192))
    expected['number_of_stages_using_block_ram_for_data_and_phase_factors']=str(profile.get('fft_bram_stages',6))
    actual = json.loads(XCI.read_text(encoding="utf-8"))["ip_inst"]["parameters"]["component_parameters"]
    for name, value in expected.items():
        if name not in actual or actual[name][0]["value"].lower() != value.lower():
            raise ValueError(f"FFT XCI disagrees with create_fft.tcl: {name}; regenerate the FFT IP before building")
    return expected


if __name__ == "__main__":
    print("FFT_CONFIGURATION_PASS", len(check()))
