"""Exact OFDM board qualification using the unchanged production capture and oracle checker."""
import argparse
import contextlib
import datetime
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from phase4_prepare_bandwidth import ROOT,load_index,read,save,require
from fft_reference import digest,FS,N
from validate_measurements import check_bindings,configuration,verify_configuration
from qualification_capture import capture as capture_configured
from verify_board_capture import verify as verify_capture
from package_release import check
from record_boot_stage import verify_boot
from package_validated import check_board
import iq_client


def statistics(folder,row,oracle):
    records=np.fromfile(folder/'frequency.bin',dtype='<u4').reshape(-1,32)
    rows=[]
    for wid in range(4):
        selected=records[np.arange(len(records))%4==wid]
        if not len(selected):continue
        width=selected[:,17]
        normal=selected[:,1]==0
        rows.append(dict(window_id=wid,region=row['details']['windows'][wid]['region'],
            records=len(selected),normal_records=int(normal.sum()),flags=sorted(int(v) for v in np.unique(selected[:,1])),
            bandwidth_min_hz=int(width.min()),bandwidth_median_hz=float(np.median(width)),bandwidth_max_hz=int(width.max()),
            floating_bandwidth_hz=oracle['algorithm'][wid]['bandwidth_hz'],
            fixed_float_bandwidth_difference_hz=float(width[0])-oracle['algorithm'][wid]['bandwidth_hz']))
    eligible=[w for w in rows if w['region']=='internal']
    qualifies=not row['case']['crosses_nyquist'] and bool(eligible) and all(w['normal_records']==w['records'] and w['bandwidth_min_hz']>=90000000 for w in eligible)
    return dict(windows=rows,all_internal_windows_at_least_90mhz=qualifies,
        applicability='NYQUIST_WRAP_EXCLUDED' if row['case']['crosses_nyquist'] else 'UNWRAPPED',
        independent_input_seed=row['case']['seed'],cyclic_repetition_adds_independent_samples=False)


def capture(index_path,out,board):
    index_path=index_path.resolve();index=load_index(index_path)
    check();verify_boot();accepted=check_board();require(accepted['board']==board,'Different board target')
    out=out.resolve();require(out.is_relative_to(ROOT/'captures'),'Use captures/');out.mkdir(parents=True,exist_ok=False)
    paths=[ROOT/'reports'/n for n in ('hardware_provenance.json','simulation_provenance.json','boot_provenance.json',
        'current_board_validation.json','current_deployment.json')]
    report=dict(status='RUNNING',started_at=datetime.datetime.now().astimezone().isoformat(),references=str(index_path),
        references_sha256=digest(index_path),build_evidence={str(p):digest(p) for p in paths},legacy_cases=[],cases=[])
    def checkpoint():save(out/'measurement_validation.json',report)
    checkpoint()
    try:
        info=configuration(board,5001);require(info['state']&7==0,'Another controller is active')
        require(info['hardware']==accepted['hardware'],'Board identity differs');report['initial_hardware']=info
        for case in read(ROOT/'data/golden_results.json')['cases']:
            label='legacy_'+case['name']+'_'+case['mode'];folder=out/label
            print('LEGACY_START',label,flush=True)
            with (out/(label+'.log')).open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log):
                iq_client.capture(SimpleNamespace(board=board,port=5001,vector=str(ROOT/'data/vectors'/(case['name']+'.bin')),
                    out=str(folder),window=case['mode'],cyclic=False,seconds=1,detector='threshold',gap_min=32))
            result=verify_capture(folder);require(result['maximum_analysis_us']<190,'Unexpected hardware latency')
            save(folder/'measurement_validation.json',result);report['legacy_cases'].append(result);checkpoint()
        for row in index['cases']:
            case=row['case'];label=row['label'];folder=out/label;oracle=read(row['reference'])
            require(case['seconds'] in (1,10,60,300),'Unreviewed capture duration')
            print('OFDM_START',label,flush=True)
            with (out/(label+'.log')).open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log):
                capture_configured(SimpleNamespace(board=board,port=5001,vector=row['vector'],out=str(folder),
                    window=oracle['mode'],cyclic=case['replay']=='cyclic',seconds=case['seconds'],
                    detector='threshold',gap_min=32),case['detector'])
            save(folder/'configuration.json',configuration(board,5001))
            verify_configuration(folder,dict(case,applied_detector=case['detector']),oracle['mode'])
            result=verify_capture(folder,row['vector'],qualification=row['reference'])
            require(result['maximum_analysis_us']<=190 and result['maximum_publish_us']<=190,'Latency protection exceeded')
            result.update(label=label,configuration_sha256=digest(folder/'configuration.json'),
                reference_sha256=digest(row['reference']),bandwidth=statistics(folder,row,oracle))
            save(folder/'measurement_validation.json',result);report['cases'].append(result);checkpoint()
        check_bindings(report['build_evidence']);check_bindings(index['bindings'])
        report['status']='PASS'
    except Exception as error:
        report.update(status='FAIL',error=str(error));raise
    finally:
        report['finished_at']=datetime.datetime.now().astimezone().isoformat();checkpoint()
    print('PHASE4_OFDM_MATRIX_PASS',out,flush=True)


def verify(out):
    report=read(out/'measurement_validation.json');require(report['status']=='PASS','Matrix incomplete')
    check_bindings(report['build_evidence']);require(digest(report['references'])==report['references_sha256'],'Index changed')
    index=load_index(Path(report['references']));require(len(report['cases'])==len(index['cases']) and len(report['legacy_cases'])==16,'Case count differs')
    for row in report['legacy_cases']:
        require(verify_capture(row['folder'])==row,'Legacy verification changed')
    for row,previous in zip(index['cases'],report['cases']):
        folder=Path(previous['folder']);require(previous['label']==row['label'],'Order changed')
        require(digest(folder/'configuration.json')==previous['configuration_sha256'],'Configuration changed')
        verify_configuration(folder,dict(row['case'],applied_detector=row['case']['detector']),read(row['reference'])['mode'])
        actual=verify_capture(folder,row['vector'],qualification=row['reference'])
        require(all(previous[k]==v for k,v in actual.items()),'Exact capture changed')
        require(statistics(folder,row,read(row['reference']))==previous['bandwidth'],'Bandwidth statistics changed')
    print('PHASE4_OFDM_VERIFY_PASS',out)


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('capture','verify'));p.add_argument('--references',type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--board',default='192.168.1.10');a=p.parse_args()
    if a.action=='capture':capture(a.references,a.out,a.board)
    else:verify(a.out.resolve())


if __name__=='__main__':main()
