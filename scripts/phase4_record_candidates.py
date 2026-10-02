"""Record completed isolated candidates with explicit promotion boundaries."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'build/phase4_candidate_evidence_20260922'
out.mkdir(exist_ok=False)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
evidence={}
for label, tree in (('scan',Path('D:/fft/iq_phase4_scan')),('clock125',Path('D:/fft/iq_phase4_clock125'))):
    names=['reports/hardware_validation.json','reports/hardware_provenance.json',
           'reports/worst_paths.rpt','reports/timing_summary.rpt','reports/utilization_flat.rpt']
    if label=='scan':names+=['reports/current_board_validation.json','reports/current_deployment.json',
        'reports/simulation_provenance.json','reports/phase2_latency_validation.json']
    for name in names:
        dst=out/label/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(tree/name,dst)
        evidence[dst.relative_to(ROOT).as_posix()]=sha(dst)
scan=read(out/'scan/reports/current_board_validation.json')
clock=read(out/'clock125/reports/hardware_validation.json')
assert scan['status']=='PASS' and len(scan['cases'])==36
assert scan['maximum_analysis_us']<=178 and clock['setup_slack_ns']<.1
matrix=ROOT/'build/phase4_clock_matrix_20260922_v4/clock_matrix.csv'
evidence[matrix.relative_to(ROOT).as_posix()]=sha(matrix)
report=dict(status='PASS',created_at=datetime.datetime.now().astimezone().isoformat(),
    eight_lane=dict(status='ELIGIBLE_FOR_COMPOSITION',full_simulation=True,basic_board_cases=36,
        maximum_analysis_us=scan['maximum_analysis_us'],maximum_publish_us=scan['maximum_publish_us'],
        improvement_us=round(183.41-scan['maximum_analysis_us'],2),
        hardware=read(out/'scan/reports/hardware_validation.json'),
        limitation='Does not replace the combined build full matrix and physical cold start'),
    clock125=dict(status='NOT_PROMOTED',actual_source_hz=125000000,actual_fft_hz=125000000,
        hardware=clock,required_setup_slack_ns=.1,
        reason='0.029 ns setup margin below the 0.10 ns engineering promotion gate',
        critical_path='gap_min register to digital_detector burst_data clock enable in source domain',
        critical_path_delay_ns=7.591,logic_levels=11,route_fraction_percent=62.523,
        board_programmed=False,metadata_parameterization_complete=False,
        scope='Physical timing feasibility only; a nonnegative STA report is not 125 MSPS board acceptance'),
    evidence=evidence)
(ROOT/'reports/phase4_candidate_decisions.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('ISOLATED_CANDIDATE_DECISIONS_RECORDED')
