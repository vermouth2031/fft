"""Assemble the two isolated Phase 4 source changes for independent qualification."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

target = Path('D:/fft/iq_phase4_combined')
rate = Path('D:/fft/iq_phase4_rate')
scan = Path('D:/fft/iq_phase4_scan')
assert target.is_dir() and not (target / 'build').exists(), 'Expected new isolated worktree'
names = subprocess.check_output(['git', 'diff', '--name-only', '--', 'rtl', 'constraints',
    'firmware', 'host', 'tests', 'scripts'], cwd=rate, text=True).splitlines()
names += ['config/build_profile.json', 'rtl/iq_build_config.sv', 'scripts/phase4_build_config.py',
          'scripts/phase4_identity.py', 'scripts/phase4_test_identity.py']
provenance = {}
for name in names:
    dest = target / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rate / name, dest)
    provenance[name] = {'source': str(rate / name), 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}
for name in ('rtl/spectrum_measure.sv', 'tests/tb_spectrum_edges.sv', 'scripts/analyze_latency.py'):
    shutil.copy2(scan / name, target / name)
    provenance[name] = {'source': str(scan / name), 'sha256': hashlib.sha256((target / name).read_bytes()).hexdigest()}
p = target / 'tests/tb_core.sv'
b = p.read_bytes()
assert b.count(b'compare_addr==2047') == 1
p.write_bytes(b.replace(b'compare_addr==2047', b'compare_addr==1023'))
p = target / 'config/build_profile.json'
profile = json.loads(p.read_text()); profile['scan_lanes'] = 8
p.write_text(json.dumps(profile, indent=2) + '\n')
(target / 'build').mkdir()
(target / 'build/phase4_composition.json').write_text(json.dumps(dict(
    scope='Composition only. Requires new full simulation, implementation and board qualification.',
    inputs=provenance, edits=['tb_core scan termination 1023; preserve rate counters', 'profile scan_lanes=8']), indent=2))
subprocess.run(['python', 'scripts/phase4_build_config.py'], cwd=target, check=True)
print('COMBINED_SOURCE_PREPARED')
