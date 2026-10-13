"""Freeze the fully tested 150 MHz structural control before the 160 MHz trial."""
from pathlib import Path
import datetime
import json
import re
import shutil
from record_build_stage import verify, sha

ROOT=Path(__file__).resolve().parents[1]

def main():
    stages={stage:verify(stage) for stage in ('simulation','hardware')}
    read=lambda name:json.loads((ROOT/name).read_text(encoding='utf-8'))
    profile=read('config/build_profile.json')
    assert profile['sample_rate_hz']==profile['fft_clock_hz']==profile['timestamp_clock_hz']==150000000
    assert profile['hardware_version']==65547 and profile['fft_length']==16384
    assert profile['scan_lanes']==8 and profile['input_fifo_depth']==4096
    assert profile['replay_bank_samples']==32768 and profile['frequency_records']==128
    core,hardware=read('reports/core_validation.json'),read('reports/hardware_validation.json')
    assert core['status']=='PASS' and core['exact_fft_points']==1048576 and core['frequency_records']==64
    assert core['maximum_analysis_latency_us']<=234.426667
    assert hardware['status']=='PASS' and hardware['setup_slack_ns']>=0 and hardware['hold_slack_ns']>=0
    assert hardware['cdc_critical']==hardware['unconstrained_internal_endpoints']==0
    resources={}
    text=(ROOT/'reports/utilization_flat.rpt').read_text()
    for label,maximum in [('Slice LUTs',23400),('Slice Registers',29200),('Block RAM Tile',128),('DSPs',49)]:
        match=re.search(r'\|\s*'+re.escape(label)+r'\*?\s*\|\s*([\d.]+)',text)
        assert match,label
        resources[label]=float(match[1]);assert resources[label]<=maximum,(label,resources[label])
    log=(ROOT/'build/logs/sim_phase13_commit.log').read_text(errors='replace')
    assert 'PHASE13_COMMIT_PASS transactions=64 cancel_stages=3' in log and 'Fatal:' not in log
    axi=(ROOT/'build/logs/sim_axi.log').read_text(errors='replace')
    assert 'AXI_PASS' in axi and 'ACK_INTERVAL_PASS cases=65536' in axi and 'Fatal:' not in axi
    destination=ROOT/'reports/phase13_structural150_evidence'
    assert not destination.exists(),'Keep each trial immutable; review existing archive first'
    names={f'reports/{s}_provenance.json' for s in stages}
    for stage in stages.values():
        names.update(stage['inputs']);names.update(stage['evidence'])
    for group in read('build/logs/core_parallel_manifest.json')['groups']:
        log=Path(group['log']).resolve()
        assert log.is_relative_to(ROOT) and sha(log)==group['sha256']
        names.add(log.relative_to(ROOT).as_posix())
    for test in read('reports/phase9_python_validation.json')['tests']:
        assert test['exit_code']==0 and sha(ROOT/test['log'])==test['sha256']
        names.add(test['log'])
    names.add('scripts/phase13_archive_structural.py')
    files={}
    for name in sorted(names):
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
        files[target.relative_to(ROOT).as_posix()]=sha(target)
    artifacts=ROOT/'build/trials/structural150/artifacts'
    artifacts.mkdir(parents=True,exist_ok=False)
    for name,expected in stages['hardware']['artifacts'].items():
        assert sha(ROOT/name)==expected
        shutil.copyfile(ROOT/name,artifacts/Path(name).name)
    report=dict(status='STRUCTURAL_150_SIMULATION_AND_TIMING_PASS',
        created_at=datetime.datetime.now().astimezone().isoformat(),
        build_id=read('build/config/build_identity.json')['build_id'],
        profile=profile,resources=resources,hardware=hardware,simulation=core,
        board_programmed=False,sd_installed=False,
        artifacts=stages['hardware']['artifacts'],files=files)
    (ROOT/'reports/phase13_structural150_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PHASE13_STRUCTURAL150_ARCHIVED',report['build_id'],resources,hardware)

if __name__=='__main__':main()
