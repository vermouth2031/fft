"""Qualify the timing candidate through one serialized physical-board workflow."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from iq_client import Client
from record_build_stage import sha


def run(name,command):
    log=ROOT/'build/logs'/('phase5_'+name+'.log')
    attempt=1
    while log.exists():
        attempt+=1
        log=ROOT/'build/logs'/f'phase5_{name}_attempt{attempt}.log'
    print('COMPATIBLE_STAGE_START',name,flush=True)
    with log.open('x',encoding='utf-8') as stream:
        result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(f'{name} failed: {log}')
    print('COMPATIBLE_STAGE_PASS',name,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-packaged',action='store_true',help='Verify and reuse the already packaged matching image')
    args=parser.parse_args()
    # Waiting does not access the board. The run.ps1 marker follows every check
    # and provenance recording, and is unique to the final bounded attempt.
    log=ROOT/'phase5_sim_attempt3.log';deadline=time.monotonic()+3600
    while True:
        raw=log.read_bytes();text=raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-8',errors='replace')
        if 'Completed stage: Sim' in text:break
        if 'Vivado failed:' in text or 'Python failed:' in text:raise RuntimeError('Final simulation failed')
        if time.monotonic()>deadline:raise TimeoutError('Simulation completion wait expired')
        time.sleep(5)
    hw=json.loads((ROOT/'reports/hardware_validation.json').read_text())
    assert hw['status']=='PASS' and hw['setup_slack_ns']>=.4 and hw['hold_slack_ns']>=0
    py=[sys.executable,'-X','utf8']
    if args.resume_packaged:
        from package_release import check
        from record_boot_stage import verify_boot
        check();verify_boot()
    else:
        run('package',['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/run.ps1','-Action','Package'])
    run('workspace_audit',py+['scripts/phase5_audit_workspace.py','--references-root','build/phase5/final_r2_3'])
    client=Client('192.168.1.10')
    try:
        if client.read(8)[0]&7:raise RuntimeError('Board has an active capture; candidate not loaded')
    finally:client.close()
    run('clock100',py+['scripts/maintenance/measure_clock.py','--out','captures/phase5/clock100'])
    run('deploy100',py+['scripts/deploy_board.py'])
    run('basic100',py+['scripts/validate_board.py','--suite','full','--out','captures/phase5/basic100'])
    board=json.loads((ROOT/'reports/current_board_validation.json').read_text())
    assert board['status']=='PASS' and len(board['cases'])==36 and board['maximum_analysis_us']<=175.5
    path=ROOT/'reports/phase5_detector_timing.json';result=json.loads(path.read_text())
    result.update(status='R2_PASS_ELIGIBLE_FOR_RATE_EXPERIMENT',basic_board_cases=36,
                  maximum_analysis_us=board['maximum_analysis_us'],maximum_publish_us=board['maximum_publish_us'],
                  board_report_sha256=sha(ROOT/'reports/current_board_validation.json'),
                  clock_report='captures/phase5/clock100/clock_validation.json',
                  limitation='Full final matrix and SD/cold-start delivery remain separate gates')
    path.write_text(json.dumps(result,indent=2)+'\n')
    print('R2_COMPATIBLE_QUALIFICATION_PASS',flush=True)


if __name__=='__main__':main()
