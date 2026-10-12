"""Reuse an early AXI run only for identical compiled HDL, stimulus, ROM and FFT.

The full successful log and original simulation script remain bound evidence.
A clock, HDL, test or IP change always causes a fresh run.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'build/phase13_axi_cache'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs():
    paths=list((ROOT/'rtl').glob('*.sv'))+list((ROOT/'rtl').glob('*.svh'))
    paths += [ROOT/n for n in ('tests/tb_axi.sv','data/hann_quarter_u18_f17.mem',
        'build/vivado16k/iq_analyzer.srcs/sources_1/ip/fft8192/fft8192.xci')]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)}
def validate_log(text):
    assert 'AXI_PASS' in text and 'ACK_INTERVAL_PASS cases=65536' in text and 'Fatal:' not in text
def register():
    log=ROOT/'build/logs/early_axi.log'
    validate_log(log.read_text(errors='replace'))
    compiled=ROOT/'build/axi_test/axi_test.sim/sim_1/behav/xsim/compile.log'
    bound=inputs()
    assert all((ROOT/n).stat().st_mtime_ns<=compiled.stat().st_mtime_ns for n in bound), 'Input edited after early AXI compilation'
    CACHE.mkdir(exist_ok=False)
    for source,name in [(log,'early_axi.log'),(ROOT/'scripts/sim_axi.tcl','original_sim_axi.tcl'),
        (ROOT/'build/axi_test/axi_test.sim/sim_1/behav/xsim/simulate.log','simulate.log')]:
        shutil.copyfile(source,CACHE/name)
    record=dict(inputs=bound,proof={p.name:sha(p) for p in CACHE.iterdir()},
        scope='Successful early AXI run reused at the same input bytes; no hardware programming')
    (CACHE/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print('PHASE13_AXI_CACHE_REGISTERED')
def reuse():
    record=json.loads((CACHE/'manifest.json').read_text())
    assert inputs()==record['inputs'],'AXI inputs changed'
    assert all(sha(CACHE/n)==h for n,h in record['proof'].items()),'AXI evidence changed'
    original=(CACHE/'original_sim_axi.tcl').read_text()
    assert (ROOT/'scripts/sim_axi.tcl').read_text().endswith(original),'Simulation recipe changed'
    text=(CACHE/'early_axi.log').read_text(errors='replace');validate_log(text)
    for line in text.splitlines():
        if line.startswith(('AXI_PASS','ACK_INTERVAL_PASS')):print(line)
    print('PHASE13_AXI_REUSE_PASS manifest_sha256='+sha(CACHE/'manifest.json'))
if __name__=='__main__':
    try:
        if sys.argv[1]=='register':register()
        elif sys.argv[1]=='reuse':reuse()
        else:raise ValueError('register or reuse required')
    except (AssertionError,FileNotFoundError,ValueError) as error:
        print('PHASE13_AXI_CACHE_MISS',error);sys.exit(1)
