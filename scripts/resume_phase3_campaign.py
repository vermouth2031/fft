"""Resume the interrupted 2026-09-21 campaign with the identical accepted build."""
import datetime
import json
from pathlib import Path
import subprocess
import sys

from package_validated import check_board, require
from record_build_stage import ROOT, sha
from validate_measurements import check_bindings


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    root = ROOT/'captures/phase3_complete_20260921'
    refs = ROOT/'build/phase3_final_20260921'
    path = root/'campaign.json'
    campaign = read(path)
    require(campaign['status']=='RUNNING', 'Only the interrupted campaign can resume')
    expected = ['board','extended','gui','validation','noise_only','legacy_regression','robust_regression']
    require([r['stage'] for r in campaign['stages']]==expected, 'Unexpected completed stages')
    for row in campaign['stages']:
        require(row['status']=='PASS' and sha(Path(row['log']))==row['log_sha256'], 'Completed stage changed')
    accepted = check_board()
    recovery_path = root/'recovery_deployment_20260922.json'
    recovery = read(recovery_path)
    require(recovery['status']=='PASS' and recovery['hardware']==accepted['hardware'], 'Recovery deployment failed')
    require(recovery['artifacts']==accepted['deployment']['artifacts'], 'Recovery build differs')
    require(sha(Path(recovery['log']))==recovery['log_sha256'], 'Recovery log changed')
    for stage in expected[3:]:
        previous = read(root/stage/'measurement_validation.json')
        require(previous['status']=='PASS', 'Prior matrix did not pass')
        for field in ('bindings','artifacts','build_evidence'):
            check_bindings(previous[field])
    interrupted = root/'wide_continuous'
    archived = root/'wide_continuous_interrupted_20260921'
    require(interrupted.resolve().is_relative_to(root) and archived.resolve().is_relative_to(root), 'Archive outside campaign')
    require(not archived.exists(), 'Interruption already archived')
    original = path.read_bytes()
    (root/'campaign_interrupted_20260921.json').write_bytes(original)
    interrupted.rename(archived)
    (root/'wide_continuous.log').rename(root/'wide_continuous_interrupted_20260921.log')
    campaign['recovery'] = dict(
        reason='Previous process ended during the final wide continuous case; no matrix PASS was recorded. Network command query timed out on continuation; identical artifacts reloaded through JTAG.',
        prior_campaign_sha256=sha(root/'campaign_interrupted_20260921.json'),
        archived_partial=str(archived), archived_metadata_paths='Original paths retained verbatim; this incomplete matrix is excluded from acceptance.',
        deployment=str(recovery_path), deployment_sha256=sha(recovery_path),
        driver_sha256=sha(Path(__file__)), resumed_at=datetime.datetime.now().astimezone().isoformat())
    save(path, campaign)
    jobs = [(stage, ['scripts/validate_measurements.py','capture','--references',str(refs/stage/'references/index.json'),
                    '--out',str(root/stage),'--board',campaign['board']]) for stage in ('wide_continuous','sensitivity')]
    jobs.append(('frame_lengths',['scripts/analyze_frame_lengths.py']))
    try:
        for stage, command in jobs:
            print('PHASE3_RESUME_START',stage,flush=True)
            log=root/(stage+'.log')
            with log.open('w',encoding='utf-8') as stream:
                result=subprocess.run([sys.executable,'-X','utf8',*command],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            campaign['stages'].append(dict(stage=stage,status='PASS' if result.returncode==0 else 'FAIL',
                log=str(log),log_sha256=sha(log),finished_at=datetime.datetime.now().astimezone().isoformat()))
            save(path,campaign)
            require(result.returncode==0, f'Resumed stage failed: {stage}; inspect {log}')
            print('PHASE3_RESUME_PASS',stage,flush=True)
        campaign['status']='PASS'
    except Exception as error:
        campaign.update(status='FAIL',error=str(error))
        raise
    finally:
        campaign['finished_at']=datetime.datetime.now().astimezone().isoformat()
        save(path,campaign)


if __name__=='__main__':
    main()
