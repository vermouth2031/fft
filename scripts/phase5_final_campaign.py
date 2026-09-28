"""Regenerate frozen regression inputs and qualify the phase-five compatible build."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
from record_build_stage import ROOT,sha
from package_release import check
from record_boot_stage import verify_boot

REFS=ROOT/'build/phase5/final'
CAPTURES=ROOT/'captures/phase5/final'

def run(command,log):
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('x',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,'-X','utf8',*map(str,command)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Stage failed: '+str(log))

def prepare():
    # Mathematical references may be prepared before the hardware build finishes.
    profile=json.loads((ROOT/'config/build_profile.json').read_text())
    assert profile['scan_lanes']==8 and profile['sample_rate_hz']==100000000
    REFS.mkdir(parents=True,exist_ok=False)
    for name,script in (('regression','phase3_prepare_release.py'),('ofdm','phase4_prepare_bandwidth.py'),('widest','phase4_prepare_widest.py')):
        print('PHASE5_FINAL_REFERENCE_START',name,flush=True)
        run(['scripts/'+script,'--out',REFS/name],REFS/(name+'_prepare.log'))
    from validate_measurements import prepare as make_reference
    from generate_qualification_vectors import generate
    noise_manifest=generate(ROOT/'config/phase5_regression_noise_spec.json',REFS/'noise/vectors')
    make_reference(noise_manifest,REFS/'noise/references')
    (REFS/'prepared.json').write_text(json.dumps(dict(status='PASS',profile=profile,
        generator_sha256=sha(Path(__file__)),scope='Known regression seeds reused; not additional independent validation'),indent=2))
    print('PHASE5_FINAL_REFERENCES_READY',flush=True)

def capture():
    check();verify_boot()
    assert json.loads((REFS/'prepared.json').read_text())['status']=='PASS'
    CAPTURES.mkdir(parents=True,exist_ok=False)
    report=dict(status='RUNNING',started_at=datetime.datetime.now().astimezone().isoformat(),stages=[],
                driver_sha256=sha(Path(__file__)))
    def save():(CAPTURES/'phase5_campaign.json').write_text(json.dumps(report,indent=2)+'\n')
    def stage(name,command):
        print('PHASE5_FINAL_STAGE_START',name,flush=True)
        log=CAPTURES/(name+'.log');run(command,log)
        report['stages'].append(dict(stage=name,status='PASS',log=str(log),log_sha256=sha(log)));save()
        print('PHASE5_FINAL_STAGE_PASS',name,flush=True)
    save()
    try:
        stage('regression',['scripts/phase3_board_campaign.py','--references-root',REFS/'regression','--out',CAPTURES/'regression'])
        def ofdm(name,index):stage(name,['scripts/phase4_validate_bandwidth.py','capture','--references',index,'--out',CAPTURES/name])
        ofdm('ofdm_finite',REFS/'ofdm/finite/index.json')
        ofdm('ofdm_boundary',REFS/'ofdm/boundary/index.json')
        stage('prepare_ofdm_continuous',['scripts/phase4_prepare_continuous.py','--root',REFS/'ofdm',
                                        '--finite',CAPTURES/'ofdm_finite/measurement_validation.json'])
        ofdm('ofdm_continuous',REFS/'ofdm/continuous/index.json')
        ofdm('widest_finite',REFS/'widest/finite/index.json')
        from phase4_prepare_widest import spec
        from phase4_prepare_bandwidth import prepare as make_reference
        finite=json.loads((CAPTURES/'widest_finite/measurement_validation.json').read_text())
        assert finite['status']=='PASS' and len(finite['cases'])==80
        for row in finite['cases']:
            assert row['bandwidth']['applicability']=='UNWRAPPED'
            assert all(w['normal_records']==w['records'] and w['bandwidth_min_hz']>=95000000
                       for w in row['bandwidth']['windows'] if w['region']=='internal')
        train=REFS/'widest/training.json';gain=json.loads(train.read_text())['gain']
        cases=[]
        for mode in ('qpsk','qam16'):
            cases += [spec(212100,mode,gain,10),spec(212100,mode,gain,60,('hann',))]
        cases.append(spec(212100,'qpsk',gain,300,('hann',)))
        make_reference(cases,REFS/'widest/continuous',train)
        ofdm('widest_continuous',REFS/'widest/continuous/index.json')
        stage('noise',['scripts/validate_measurements.py','capture','--references',REFS/'noise/references/index.json',
                       '--out',CAPTURES/'noise'])
        report['status']='PASS'
    except Exception as e:
        report.update(status='FAIL',error=str(e));raise
    finally:
        report['finished_at']=datetime.datetime.now().astimezone().isoformat();save()
    print('PHASE5_FINAL_BOARD_CAMPAIGN_PASS',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','capture'))
    p.add_argument('--references-root',type=Path,default=REFS)
    p.add_argument('--captures-root',type=Path,default=CAPTURES)
    a=p.parse_args();REFS=a.references_root.resolve();CAPTURES=a.captures_root.resolve()
    if not REFS.is_relative_to(ROOT/'build') or not CAPTURES.is_relative_to(ROOT/'captures'):
        p.error('References and captures must remain inside their project roots')
    {'prepare':prepare,'capture':capture}[a.action]()
