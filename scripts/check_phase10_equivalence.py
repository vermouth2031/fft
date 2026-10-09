"""Record the cross-version spectrum regression and its bounded queue occupancy."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
log=ROOT/'build/logs/sim_phase10_equivalence.log'
text=log.read_text(errors='replace')
m=re.search(r'PHASE10_EQUIVALENCE_PASS cycles=(\d+) queue_high_water=(\d+)',text)
lat=re.search(r'last_to_result_cycles=(\d+)\.\.(\d+)',text)
assert m and 'Fatal:' not in text,'Cross-version equivalence did not pass'
assert lat and int(lat[1])==int(lat[2])==2127,'Spectrum latency changed'
assert int(m[2])<=2123,'Unexpected scan-overlap queue occupancy'
paths=['rtl/spectrum_measure.sv','rtl/spectrum_store.sv','rtl/spectrum_lane.sv',
       'tests/tb_phase10_equivalence.sv','tests/reference/phase9_spectrum_measure.sv',
       'scripts/sim_phase10_equivalence.tcl','scripts/check_phase10_equivalence.py',
       'build/logs/sim_phase10_equivalence.log']
r=dict(status='PASS',baseline_commit='c22f9e0af6c297762b0ca7aa59f08548beecb44e',
       cycles_compared=int(m[1]),queue_high_water=int(m[2]),queue_capacity=2560,
       spectrum_latency_cycles=2127,
       scope='Cycle-exact result/snapshot/control equivalence; bit-reversed and natural order, bubbles, reset during scan/queue/refill',
       files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
(ROOT/'reports/phase10_equivalence.json').write_text(json.dumps(r,indent=2)+'\n')
print('PHASE10_EQUIVALENCE_RECORDED',r['cycles_compared'],r['queue_high_water'])
