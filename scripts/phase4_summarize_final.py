"""Check byte-bound final matrix evidence and summarize one combined hardware build."""
import argparse
import collections
import datetime
import json
from pathlib import Path
from record_build_stage import ROOT,sha
from package_release import check
from package_validated import check_board
from phase4_final_campaign import REFS,CAPTURES

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def require(ok,message):
    if not ok:raise ValueError(message)

def verify_report(path):
    report=read(path)
    require(report['status']=='PASS' and report['schema']=='iq-phase4-final-measurements-v1','Incomplete final evidence')
    check();board=check_board()
    require(board['hardware']==report['hardware'],'Final report hardware mismatch')
    for name,digest in report['evidence'].items():
        p=(ROOT/name).resolve();require(p.is_relative_to(ROOT) and sha(p)==digest,'Evidence changed: '+name)
    return report

def summarize():
    from summarize_phase3 import summarize as regression_summary
    from phase4_prepare_bandwidth import load_index
    from validate_measurements import load_manifest,check_bindings
    check();board=check_board();campaign=read(CAPTURES/'phase4_campaign.json')
    require(campaign['status']=='PASS','Final campaign did not complete')
    require(board['hardware']['scan_lanes']==8,'Expected combined eight-lane build')
    evidence={}
    def add(p,expected=None):
        p=Path(p).resolve();require(p.is_relative_to(ROOT),'Evidence outside project')
        digest=sha(p)
        if expected is not None:require(digest==expected,'Changed evidence: '+str(p))
        evidence[p.relative_to(ROOT).as_posix()]=digest
    regression=regression_summary(CAPTURES/'regression',False)
    require(regression['targets_met'],'A regression target failed')
    regression['scope']='Known Phase 3 seed sets rerun on the Phase 4 eight-lane build; not new independent seeds'
    matrices=[];all_cases=list(board['cases'])
    for row in regression['stages']:
        path=Path(row['folder'])/'measurement_validation.json';matrix=read(path)
        matrices.append(dict(stage='regression/'+row['stage'],cases=len(matrix['cases']),legacy_cases=len(matrix['legacy_cases'])))
        all_cases+=matrix['cases']+matrix['legacy_cases']
    groups=collections.defaultdict(list)
    names_counts=(('ofdm_finite',240),('ofdm_boundary',24),('ofdm_continuous',7),('widest_finite',80),('widest_continuous',7),('noise',9))
    for name,count in names_counts:
        matrix=read(CAPTURES/name/'measurement_validation.json')
        require(matrix['status']=='PASS' and len(matrix['cases'])==count and len(matrix['legacy_cases'])==16,'Incomplete '+name)
        check_bindings(matrix['build_evidence'])
        require(sha(Path(matrix['references']))==matrix['references_sha256'],'Reference index changed')
        if name!='noise':load_index(Path(matrix['references']))
        else:
            check_bindings(matrix['bindings']);check_bindings(matrix['artifacts'])
            index=read(matrix['references']);load_manifest(index['manifest']);check_bindings(index['bindings'])
        matrices.append(dict(stage=name,cases=count,legacy_cases=16))
        all_cases+=matrix['cases']+matrix['legacy_cases']
        if name in ('ofdm_finite','widest_finite','widest_continuous'):
            for row in matrix['cases']:
                parts=row['label'].split('_');key=parts[1]+'_'+parts[2]+'_'+parts[-1]
                for window in row['bandwidth']['windows']:
                    if window['region']!='internal':continue
                    require(window['normal_records']==window['records'],'Flagged internal window')
                    if name.startswith('widest'):require(window['bandwidth_min_hz']>=95000000,'95 MHz target failed')
                    if name!='widest_continuous':groups[key].append(window['bandwidth_min_hz'])
    high_water=[];sample_counts=[]
    for row in all_cases:
        require(row['status']=='PASS','Failed numerical row')
        folder=Path(row['folder'])
        for name,digest in row['files'].items():add(folder/name,digest)
        if 'configuration_sha256' in row:add(folder/'configuration.json',row['configuration_sha256'])
        meta=read(folder/'capture.json')
        require(meta['build_id']==board['hardware']['build_id'],'Capture belongs to another build')
        d=meta['throughput_diagnostics']
        require(meta['throughput_conservation_valid'] and
            d['issued_samples']==d['accepted_samples']==d['fft_input_samples']==d['fft_output_samples']==meta['input_samples']==8192*d['fft_output_windows'] and
            d['fft_output_windows']==meta['completed_windows'] and 0<d['input_fifo_high_water']<4096 and
            not(d['input_rejected'] or d['result_queue_rejected'] or d['input_underreads']),'Throughput conservation failed')
        high_water.append(d['input_fifo_high_water']);sample_counts.append(d['issued_samples'])
    max_analysis=max(r['maximum_analysis_us'] for r in all_cases)
    max_publish=max(r['maximum_publish_us'] for r in all_cases)
    require(max_analysis<=178 and max_publish<190,'Combined latency target failed')
    for tree in (REFS,CAPTURES):
        for path in tree.rglob('*'):
            if path.is_file() and path.name not in ('frequency.json','frequency.csv','burst.json','burst.csv'):
                add(path)
    # Noise reference deliberately reuses the frozen nine preselected inputs.
    noise_index=read(REFS/'noise/references/index.json')
    for p in Path(noise_index['manifest']).parent.rglob('*'):
        if p.is_file():add(p)
    for name in ('current_board_validation.json','current_deployment.json','hardware_provenance.json',
                 'simulation_provenance.json','software_validation.json','boot_provenance.json',
                 'phase4_candidate_import.json','phase4_requirements.json'):
        add(ROOT/'reports'/name)
    return dict(schema='iq-phase4-final-measurements-v1',status='PASS',
        created_at=datetime.datetime.now().astimezone().isoformat(),hardware=board['hardware'],
        scope='One combined build; exact regression and new OFDM/noise matrix acceptance. SD/cold start are separately required.',
        regression=regression,matrices=matrices,basic_board_cases=len(board['cases']),
        matrix_cases=sum(r['cases'] for r in matrices),legacy_check_cases=sum(r['legacy_cases'] for r in matrices),
        maximum_analysis_us=max_analysis,maximum_publish_us=max_publish,
        bandwidth={key:dict(internal_windows=len(values),min_hz=min(values),max_hz=max(values)) for key,values in groups.items()},
        minimum_widest_internal_obw_hz=min(v for k,values in groups.items() if k.startswith('b98p14') for v in values),
        ofdm_continuous_seconds=920,maximum_samples_in_one_capture=max(sample_counts),
        maximum_input_fifo_high_water=max(high_water),minimum_input_fifo_high_water=min(high_water),
        throughput_checks=len(all_cases),all_throughput_conservation_pass=True,evidence=evidence)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'reports/phase4_final_measurements.json')
    p.add_argument('--check',action='store_true');a=p.parse_args()
    if a.check:verify_report(a.out)
    else:
        result=summarize();require(not a.out.exists(),'Do not overwrite a completed aggregate')
        a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PHASE4_FINAL_MEASUREMENTS_PASS',a.out,flush=True)
