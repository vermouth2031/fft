import contextlib,datetime,json
from pathlib import Path
from types import SimpleNamespace
from phase4_prepare_bandwidth import load_index,read,save,require
from phase4_validate_bandwidth import statistics
from fft_reference import digest
from validate_measurements import check_bindings,configuration,verify_configuration
from qualification_capture import capture as capture_configured
from verify_board_capture import verify as verify_capture
from package_release import check
from record_boot_stage import verify_boot
from package_validated import check_board
import iq_client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'captures/phase5/final/widest_continuous'
INDEX=ROOT/'build/phase5/final_r2_3/widest/continuous/index.json'
REPORT=OUT/'measurement_validation.json'
report=read(REPORT)
require(report['status']=='RUNNING','campaign report is not resumable')
check();verify_boot();accepted=check_board();index=load_index(INDEX)
require(report['references_sha256']==digest(INDEX),'index changed')
require(len(report['legacy_cases'])==16,'legacy cases incomplete')
completed={r['label'] for r in report['cases']}
info=configuration('192.168.1.10',5001)
require(info['state']&7==0,'board busy')
require(info['hardware']==accepted['hardware'],'board identity differs')
for row in index['cases']:
    case=row['case']; label=row['label']
    if label in completed: continue
    folder=OUT/label
    require(not folder.exists(),'case folder already exists')
    oracle=read(row['reference'])
    require(case['seconds'] in (1,10,60,300),'unreviewed duration')
    print('RESUME_OFDM_START',label,flush=True)
    with (OUT/(label+'.log')).open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log):
        capture_configured(SimpleNamespace(board='192.168.1.10',port=5001,vector=row['vector'],out=str(folder),window=oracle['mode'],cyclic=case['replay']=='cyclic',seconds=case['seconds'],detector='threshold',gap_min=32),case['detector'])
    save(folder/'configuration.json',configuration('192.168.1.10',5001))
    verify_configuration(folder,dict(case,applied_detector=case['detector']),oracle['mode'])
    result=verify_capture(folder,row['vector'],qualification=row['reference'])
    require(result['maximum_analysis_us']<=190 and result['maximum_publish_us']<=190,'latency protection exceeded')
    result.update(label=label,configuration_sha256=digest(folder/'configuration.json'),reference_sha256=digest(row['reference']),bandwidth=statistics(folder,row,oracle))
    save(folder/'measurement_validation.json',result)
    report['cases'].append(result)
    save(REPORT,report)
    print('RESUME_OFDM_PASS',label,flush=True)
require([r['label'] for r in report['cases']]==[r['label'] for r in index['cases']],'case order/count incomplete')
check_bindings(report['build_evidence']);check_bindings(index['bindings'])
report['status']='PASS';report['finished_at']=datetime.datetime.now().astimezone().isoformat();save(REPORT,report)
print('WIDEST_CONTINUOUS_RESUME_PASS',len(report['cases']),flush=True)
