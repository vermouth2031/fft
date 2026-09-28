"""Build and execute a RAM-only CPU/2 versus PL clock probe using this BSP."""
import argparse
import json
from pathlib import Path
import re
import struct
from sd_boot_update import ROOT, HERE, discover, require, sha, save, run_logged
from package_release import check


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--compare', type=Path, help='Previous independent-clock report; require unchanged CPU PLL/divider')
    a = p.parse_args()
    check()
    workspace, gcc, xsdb, bsp = discover()
    require(workspace.is_relative_to(ROOT), 'Clock probe must use the independent local BSP')
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    linker, count = re.subn(
        r'(ps7_ddr_0_memory_0\s*:\s*ORIGIN\s*=\s*0x100000,\s*LENGTH\s*=\s*)0x[0-9a-fA-F]+',
        lambda m: m.group(1) + '0x00f00000', (workspace / 'iq_sd/src/lscript.ld').read_text())
    require(count == 1, 'Unexpected mailbox/linker layout')
    (out / 'lscript.ld').write_text(linker)
    elf = out / 'clock.elf'
    sources = [HERE / 'measure_clock.c', HERE / 'measure_clock.tcl', Path(__file__),
               out / 'lscript.ld', bsp / 'include/xparameters.h']
    inputs = {str(path): sha(path) for path in sources}
    command = [gcc, '-DSDT', '-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard', '-O2',
               '-Wall', '-Wextra', '-Werror', f'-specs={bsp / "Xilinx.spec"}',
               '-isystem', bsp / 'include', '-L', bsp / 'lib', HERE / 'measure_clock.c',
               '-Wl,-T,' + str(out / 'lscript.ld'), '-Wl,--start-group', '-lxilstandalone',
               '-lxiltimer', '-lxil', '-lgcc', '-lc', '-Wl,--end-group', '-o', elf]
    run_logged(command, out / 'build.log', 120)
    artifacts = {n: sha(ROOT / 'artifacts' / n) for n in
                 ('iq_analyzer.bit', 'iq_analyzer.xsa', 'ps7_init.tcl')}
    save(out / 'inputs.json', dict(sources=inputs, artifacts=artifacts, elf_sha256=sha(elf), workspace=str(workspace)))
    run_logged([xsdb, HERE / 'measure_clock.tcl', elf, ROOT / 'artifacts/iq_analyzer.bit',
                ROOT / 'artifacts/iq_analyzer.xsa', ROOT / 'artifacts/ps7_init.tcl', out / 'mailbox.bin'],
               out / 'probe.log', 120)
    words = struct.unpack('<82I', (out / 'mailbox.bin').read_bytes())
    require(words[0] == 0x434c4b35 and words[1] == 2 and words[4] == 11 and words[13] == 1,
            'Invalid clock mailbox or global timer prescaler')
    build_id = ''.join(f'{x:08x}' for x in reversed(words[9:13]))
    identity = json.loads((ROOT / 'build/config/build_identity.json').read_text())
    require(build_id == identity['build_id'], 'Clock probe loaded the wrong build')
    reference_hz = words[2] / 2
    pair = lambda offset: words[offset] | words[offset + 1] << 32
    rows = [dict(ps_before=pair(16+6*n), ps_after=pair(18+6*n), pl_tick=pair(20+6*n)) for n in range(11)]
    intervals = []
    for first, last in zip(rows, rows[1:]):
        delta = last['pl_tick'] - first['pl_tick']
        low = delta * reference_hz / (last['ps_after'] - first['ps_before'])
        high = delta * reference_hz / (last['ps_before'] - first['ps_after'])
        require(low <= words[3] * 1.001 and high >= words[3] * .999, 'Clock differs from declared rate')
        require((high-low)/words[3] < .001, 'Measurement interval too uncertain')
        intervals.append(dict(hz_lower_bound=low, hz_upper_bound=high))
    cpu = dict(nominal_cpu_hz=words[2], arm_pll_ctrl=words[5], arm_clk_ctrl=words[6])
    if a.compare:
        previous = json.loads(a.compare.read_text())
        require(cpu == previous['cpu_reference'], 'CPU reference changed with the candidate')
    report = dict(status='PASS', build_id=build_id, declared_source_hz=words[3], cpu_reference=cpu,
                  fpga0_clk_ctrl=words[7], io_pll_ctrl=words[8], reference_hz=reference_hz,
                  reference='Cortex-A9 global timer CPU/2; FCLK-independent; nominal oscillator accuracy',
                  source='https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Introduction?contentId=2Ilh3ZGEcOptlhwX4Eqrhw',
                  elapsed_seconds=(rows[-1]['ps_before']-rows[0]['ps_before'])/reference_hz,
                  samples=rows, intervals=intervals, inputs_sha256=sha(out / 'inputs.json'),
                  mailbox_sha256=sha(out / 'mailbox.bin'),
                  limitation='Measures clock ratio, not absolute oscillator calibration or accepted-stream throughput',
                  comparison_sha256=sha(a.compare) if a.compare else None)
    require(inputs == {name: sha(name) for name in inputs}, 'Probe source changed during execution')
    require(artifacts == {name: sha(ROOT / 'artifacts' / name) for name in artifacts}, 'Hardware changed during probe')
    save(out / 'clock_validation.json', report)
    print('INDEPENDENT_CLOCK_PASS', words[3], intervals)


if __name__ == '__main__':
    main()
