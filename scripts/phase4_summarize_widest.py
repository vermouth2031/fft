"""Secondary >=95MHz group, durations and quantization evidence on one build."""
from pathlib import Path
import collections
import hashlib
import json
import platform
import numpy as np
from phase4_ofdm import ROOT,waveform
from phase4_prepare_bandwidth import load_index
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    capture_root=ROOT/'captures/phase4_ofdm_widest_20260922'
    reports=[json.loads((capture_root/k/'measurement_validation.json').read_text()) for k in ('finite','continuous')]
    assert all(r['status']=='PASS' for r in reports)
    assert [len(r['cases']) for r in reports]==[80,7]
    groups=collections.defaultdict(list)
    for c in reports[0]['cases']:
        assert c['bandwidth']['applicability']=='UNWRAPPED'
        for w in c['bandwidth']['windows']:
            if w['region']=='internal':
                assert w['normal_records']==w['records'] and w['bandwidth_min_hz']>=95000000
                groups[c['label'].split('_')[2]+'_'+c['label'].split('_')[-1]].append(w['bandwidth_min_hz'])
    index=load_index(ROOT/'build/phase4_ofdm_widest_20260922/finite/index.json')
    quant=[]
    for row in index['cases'][::2]:
        x,iq,details=waveform(row['case']);a,b=details['signal_interval'];v=iq[a:b].astype(np.float64)
        quant.append(dict(id=row['case']['id'],power_before_codes2=float(np.mean(abs(x[a:b])**2)),
            power_after_codes2=float(np.mean(np.sum(v*v,axis=1))),
            maximum_component_quantization_error=float(np.max(abs(np.c_[x.real,x.imag]-iq))),
            **details))
    cases=[c for r in reports for c in r['cases']+r['legacy_cases']]
    result=dict(status='PASS',scope='Secondary fixed OFDM specification; no frequency shift; existing 100MSPS hardware',
        candidate_design_span_hz=98144531.25,guard_each_side_hz=927734.375,
        minimum_internal_obw_hz=min(v for a in groups.values() for v in a),target_95mhz_met=True,
        finite_cases=80,continuous_cases=7,legacy_check_cases=32,continuous_replay_seconds=460,
        maximum_analysis_us=max(c['maximum_analysis_us'] for c in cases),
        maximum_publish_us=max(c['maximum_publish_us'] for c in cases),
        groups={k:dict(count=len(v),min_hz=min(v),median_hz=float(np.median(v)),p95_hz=float(np.percentile(v,95)),max_hz=max(v)) for k,v in groups.items()},
        evidence={str(capture_root/k/'measurement_validation.json'):sha(capture_root/k/'measurement_validation.json') for k in ('finite','continuous')},
        training_seeds=[212000,212099],validation_seeds=[212100,212119],fixed_gain=6000,
        numpy_version=np.__version__,python_version=platform.python_version(),random_bit_generator=type(np.random.default_rng().bit_generator).__name__,
        seed_domain='OFDM: numpy SeedSequence([seed,0x4f46444d]); grouped seeds across windows and constellations',
        quantization=quant)
    (ROOT/'reports/phase4_widest_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PHASE4_95MHZ_VALIDATION_PASS',result['minimum_internal_obw_hz'])
if __name__=='__main__':main()
