"""Archive the completed four-lane identity/control candidate and the rejected first composition."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
ROOT=Path(__file__).resolve().parents[1]
tree=Path('D:/fft/iq_phase4_rate')
base=ROOT/'build/phase4_candidate_evidence_20260922'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
subprocess.run(['python','scripts/package_release.py','--check'],cwd=tree,check=True)
board=read(tree/'reports/current_board_validation.json')
assert board['status']=='PASS' and len(board['cases'])==36 and board['hardware']['scan_lanes']==4
metas=[read(Path(r['folder'])/'capture.json') for r in board['cases']]
assert all(m['throughput_conservation_valid'] for m in metas)
maximum=max(m['input_samples'] for m in metas);assert maximum>2**32
out=base/'rate';out.mkdir(exist_ok=False)
names=['reports/current_board_validation.json','reports/current_deployment.json','reports/hardware_validation.json',
    'reports/hardware_provenance.json','reports/simulation_provenance.json','reports/software_validation.json']
for name in names:
    p=out/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(tree/name,p)
sources=[p for folder in ('rtl','constraints','scripts','tests','host','firmware','config','vendor/boards','data','build/config','build/logs',
                        'captures/phase4_rate_20260922') for p in (tree/folder).rglob('*')
         if p.is_file() and '__pycache__' not in p.parts and p.name not in ('frequency.json','frequency.csv','burst.json','burst.csv')]
manifest={p.relative_to(tree).as_posix():sha(p) for p in sources}
archive=out/'source_and_evidence.zip'
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for p in sources:z.write(p,p.relative_to(tree))
    z.writestr('archive_manifest.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
(out/'archive_check.json').write_text(json.dumps(dict(status='PASS',files=len(manifest),sha256=sha(archive)),indent=2))
rejected=Path('D:/fft/iq_phase4_combined/build/phase4_combined_v1_rejected')
for name in ('source.zip','decision.json','reports/hardware_validation.json','reports/worst_paths.rpt','phase4_sim_console.log'):
    p=base/'combined_v1'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(rejected/name,p)
path=ROOT/'reports/phase4_candidate_decisions.json';report=read(path)
report['identity_candidate']=dict(status='ELIGIBLE_FOR_COMPOSITION',hardware=board['hardware'],basic_board_cases=36,
    maximum_analysis_us=board['maximum_analysis_us'],maximum_publish_us=board['maximum_publish_us'],
    maximum_samples_in_one_capture=maximum,all_throughput_conservation_pass=True,
    maximum_input_fifo_high_water=max(m['throughput_diagnostics']['input_fifo_high_water'] for m in metas))
report['combined_first_implementation']=read(rejected/'decision.json')
for p in base.rglob('*'):
    if p.is_file():report['evidence'][p.relative_to(ROOT).as_posix()]=sha(p)
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('IDENTITY_CANDIDATE_ARCHIVED',maximum)
