"""Run the approved Phase 3 physical-board campaign, stopping on first failure."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
from record_build_stage import ROOT,sha
from package_release import check
from record_boot_stage import verify_boot
from summarize_phase3 import STAGES


def main():
    p=argparse.ArgumentParser();p.add_argument('--references-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--board',default='192.168.1.10');a=p.parse_args()
    check();verify_boot();out=a.out.resolve();refs=a.references_root.resolve()
    if not out.is_relative_to(ROOT/'captures'):raise ValueError('Campaign must stay in project captures/')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(status='RUNNING',started_at=datetime.datetime.now().astimezone().isoformat(),
                driver_sha256=sha(Path(__file__)),board=a.board,stages=[])
    def save():(out/'campaign.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    jobs=[('board',['scripts/validate_board.py','--suite','full','--out',str(out/'board'),'--board',a.board]),
          ('extended',['scripts/board_extended_validation.py','--out',str(out/'extended'),'--board',a.board]),
          ('gui',['scripts/check_monitor_board.py','--out',str(out/'gui'),'--board',a.board,
                  '--robust-reference-index',str(refs/'validation/references/index.json')])]
    for stage in STAGES:
        jobs.append((stage,['scripts/validate_measurements.py','capture','--references',str(refs/stage/'references/index.json'),
                            '--out',str(out/stage),'--board',a.board]))
    jobs.append(('frame_lengths',['scripts/analyze_frame_lengths.py']))
    save()
    try:
        for name,command in jobs:
            log=out/(name+'.log');print('PHASE3_CAMPAIGN_START',name,flush=True)
            with log.open('w',encoding='utf-8') as stream:
                result=subprocess.run([sys.executable,'-X','utf8',*command],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            row=dict(stage=name,status='PASS' if result.returncode==0 else 'FAIL',log=str(log),log_sha256=sha(log),
                     finished_at=datetime.datetime.now().astimezone().isoformat())
            report['stages'].append(row);save()
            if result.returncode:raise RuntimeError(f'Campaign stopped at {name}; inspect {log}')
            print('PHASE3_CAMPAIGN_PASS',name,flush=True)
        report['status']='PASS'
    except Exception as error:
        report.update(status='FAIL',error=str(error));raise
    finally:
        report['finished_at']=datetime.datetime.now().astimezone().isoformat();save()
    print('PHASE3_CAMPAIGN_COMPLETE',out)


if __name__=='__main__':main()
