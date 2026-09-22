"""Summarize the frozen Phase 3 physical-board matrices with explicit limits."""
import argparse
import collections
import datetime
import json
import math
from pathlib import Path
import numpy as np
from validate_measurements import ROOT,read,save,verify_run,check_bindings,require
from record_build_stage import sha
from summarize_phase2 import stats

STAGES=('validation','noise_only','legacy_regression','robust_regression','wide_continuous','sensitivity')
EXPECTED_COUNTS=(625,256,431,212,17,112)


def summarize(root,reverify=True):
    root=Path(root).resolve();stages=[];groups=collections.defaultdict(list)
    for stage,expected in zip(STAGES,EXPECTED_COUNTS):
        folder=root/stage
        report=verify_run(folder) if reverify else read(folder/'measurement_validation.json')
        require(report['status']=='PASS' and len(report['cases'])==expected and len(report['legacy_cases'])==16,
                'Incomplete Phase 3 stage: '+stage)
        for field in ('bindings','artifacts','build_evidence'):check_bindings(report[field])
        index=read(report['references'])
        require(sha(Path(report['references']))==report['references_sha256'],'Reference changed')
        for result,spec in zip(report['cases'],index['cases']):
            require(result['label']==spec['label'],'Case ordering changed')
            if 'detection_metrics' in result:
                groups[(stage,spec['case']['statistics_group'])].append(result['detection_metrics'])
        stages.append(dict(stage=stage,status='PASS',folder=str(folder),
            report_sha256=sha(folder/'measurement_validation.json'),references=report['references'],
            references_sha256=report['references_sha256'],cases=len(report['cases']),legacy_cases=16,
            frequency_records=sum(c['frequency_records'] for c in report['cases']),
            burst_records=sum(c['burst_records'] for c in report['cases']),
            maximum_analysis_us=max(c['maximum_analysis_us'] for c in report['cases']),
            maximum_publish_us=max(c['maximum_publish_us'] for c in report['cases'])))
        if stage=='wide_continuous':
            bandwidth=[]
            for case in report['cases']:
                records=np.fromfile(Path(case['folder'])/'frequency.bin',dtype='<u4').reshape(-1,32)
                require(len(records)==case['frequency_records'],'Wide capture length changed')
                normal=records[records[:,1]==0,17]
                require(len(normal)>0,'No normal wideband records')
                bandwidth.append(dict(label=case['label'],normal_records=len(normal),
                    flagged_records=int(np.count_nonzero(records[:,1])),
                    minimum_hz=int(normal.min()),median_hz=float(np.median(normal)),maximum_hz=int(normal.max())))
            stages[-1]['bandwidth']=bandwidth
        print('PHASE3_STAGE_VERIFIED',stage,expected,flush=True)
    detection=[]
    for (stage,name),rows in sorted(groups.items()):
        group=dict(stage=stage,group=name,cases=len(rows),seeds=sorted({r['seed'] for r in rows if r['seed'] is not None}),
                   applicability=sorted({r['applicability'] for r in rows}))
        for key in ('known_bursts','matched','normal_matches','missed','false_alarms','split_truths','merged_detections',
                    'unmatched_overlapping_detections','background_observation_us'):
            group[key]=sum(r[key] for r in rows)
        known=group['known_bursts'];duration=group['background_observation_us']/1e6
        group['normal_detection_rate']=group['normal_matches']/known if known else None
        group['false_alarms_per_second']=group['false_alarms']/duration if duration else None
        if not known and not group['false_alarms']:
            group['poisson_zero_event_upper95_per_second']=-math.log(.05)/duration
            group['upper_bound_assumption']='Poisson independent-event approximation; finite unique noise observation, not a long-term guarantee'
        for field in ('start','end','length'):
            values=[m[field+'_error_samples'] for r in rows for m in r['matches']]
            group[field+'_error_samples']=stats(values)
            group[field+'_absolute_error_samples']=stats([abs(x) for x in values])
        if stage=='validation':
            require(len(group['seeds'])==125 and known==500,'Independent validation seed/burst count differs')
            counts=np.array([[r['normal_matches'],r['known_bursts']] for r in rows])
            rng=np.random.default_rng(200000)
            samples=counts[rng.integers(0,len(rows),(4000,len(rows)))].sum(axis=1)
            group['seed_block_bootstrap95_normal_rate']=np.percentile(samples[:,0]/samples[:,1],[2.5,97.5]).tolist()
            group['bootstrap_unit']='One independently seeded input containing four bursts; resampled within this SNR group'
        detection.append(group)
    independent={g['group']:g for g in detection if g['stage']=='validation'}
    targets={f'snr{s}':independent[f'robust_snr{s}']['normal_detection_rate']>=limit for s,limit in ((30,.99),(20,.99),(10,.99),(5,.95))}
    targets['noise_only_no_false_observed']=next(g for g in detection if g['stage']=='noise_only')['false_alarms']==0
    by_group={(g['stage'],g['group']):g for g in detection}
    for snr in (30,20,10):
        before=by_group[('legacy_regression',f'validation_snr{snr}')]
        after=by_group[('robust_regression',f'robust_regression_validation_snr{snr}')]
        targets[f'high_snr{snr}_regression_not_worse']=after['normal_matches']>=before['normal_matches']
    board=read(ROOT/'reports/current_board_validation.json');hardware=read(ROOT/'reports/hardware_validation.json')
    targets['maximum_normal_analysis_below_190us']=max(board['maximum_analysis_us'],*(s['maximum_analysis_us'] for s in stages))<190
    targets['setup_slack_at_least_0p10ns']=hardware['setup_slack_ns']>=.10
    return dict(schema='iq-phase3-suite-v1',status='PASS',created_at=datetime.datetime.now().astimezone().isoformat(),
        scope='Four-lane 100MSPS hardware and explicit robust host threshold profile: exact physical-board qualification',
        algorithm_limit='Numerical PASS includes honestly recorded algorithm misses, false alarms and boundary failures; 0dB is exploratory',
        independent_validation_amplitude_codes=4096,legacy_regression_amplitude_codes=8192,
        amplitude_note='4096 chosen before training to retain int16 headroom at 0dB. Historical 8192 inputs are known regression, not new independent validation.',
        continuous_limit='Repeated 32768-pair blocks test sustained transport/compute stability; repeated blocks add no independent noise samples',
        target_results=targets,targets_met=all(targets.values()),stages=stages,detection_groups=detection,
        source_sha256=sha(Path(__file__)),evidence={})


def verify_suite(path):
    report=read(path)
    require(report.get('schema')=='iq-phase3-suite-v1' and report['status']=='PASS','Phase 3 suite has not passed')
    actual=summarize(Path(report['stages'][0]['folder']).parent,False)
    for key in ('stages','detection_groups','target_results','targets_met','source_sha256'):
        require(actual[key]==report[key],'Phase 3 summary changed: '+key)
    require(report['targets_met'],'Phase 3 profile targets did not pass')
    for name,digest in report['evidence'].items():
        path=(ROOT/name).resolve()
        require(path.is_relative_to(ROOT) and sha(path)==digest,'Phase 3 evidence changed: '+name)
    # Every stream was already numerically reverified when the aggregate was made.
    # Recheck its exact bytes here rather than repeating numerical work a third time.
    for stage in report['stages']:
        matrix=read(Path(stage['folder'])/'measurement_validation.json')
        for case in matrix['legacy_cases']+matrix['cases']:
            for name,digest in case['files'].items():
                require(sha(Path(case['folder'])/name)==digest,'Phase 3 capture changed')
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('captures',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=summarize(a.captures)
    campaign=a.captures.resolve()/'campaign.json'
    if campaign.exists():
        campaign_data=read(campaign)
        require(campaign_data['status']=='PASS','Campaign did not complete')
        result['evidence'][campaign.relative_to(ROOT).as_posix()]=sha(campaign)
        for row in campaign_data['stages']:
            log=Path(row['log'])
            require(row['status']=='PASS' and sha(log)==row['log_sha256'],'Campaign stage log changed')
            result['evidence'][log.relative_to(ROOT).as_posix()]=sha(log)
        if 'recovery' in campaign_data:
            recovery=campaign_data['recovery']
            deployment_path=Path(recovery['deployment']);deployment=read(deployment_path)
            require(sha(deployment_path)==recovery['deployment_sha256'] and deployment['status']=='PASS','Recovery deployment changed')
            require(deployment['artifacts']==read(ROOT/'reports/current_deployment.json')['artifacts'],'Recovered different artifacts')
            log=Path(deployment['log'])
            require(sha(log)==deployment['log_sha256'],'Recovery deployment log changed')
            prior=campaign.parent/'campaign_interrupted_20260921.json'
            require(sha(prior)==recovery['prior_campaign_sha256'],'Interrupted campaign record changed')
            for item in (deployment_path,log,prior,campaign.parent/'wide_continuous_interrupted_20260921.log'):
                result['evidence'][item.relative_to(ROOT).as_posix()]=sha(item)
    for directory in ('build/phase3_training_20260921','build/phase3_detector_study_20260921',
                      'build/phase3_background_study_20260921','build/phase3_clock_feasibility_20260921',
                      'build/phase3_clock_feasibility_final_20260921','build/phase3_baseline_20260921',
                      'build/phase3_timing_20260921'):
        for path in (ROOT/directory).rglob('*'):
            if path.is_file():result['evidence'][path.relative_to(ROOT).as_posix()]=sha(path)
    for name in ('reports/第三阶段完整验收报告.md','reports/第三阶段条件性优化决策.md',
                 'reports/phase2_latency_validation.json','reports/phase3_candidate_import.json','reports/phase3_reference_regeneration.json',
                 'reports/phase3_source_checkout_validation.json',
                 'build/phase3_qualification_20260921/independent_offline_validation.json'):
        path=ROOT/name
        if path.is_file():result['evidence'][name]=sha(path)
    save(a.out,result);print('PHASE3_SUITE_PASS',a.out,flush=True)


if __name__=='__main__':main()
