"""Promote only the entire predeclared secondary waveform group to duration tests."""
from pathlib import Path
import json
from phase4_prepare_widest import spec,prepare,ROOT
root=ROOT/'build/phase4_ofdm_widest_20260922'
r=json.loads((ROOT/'captures/phase4_ofdm_widest_20260922/finite/measurement_validation.json').read_text())
assert r['status']=='PASS' and len(r['cases'])==80
for c in r['cases']:
    assert not c['bandwidth']['applicability']=='NYQUIST_WRAP_EXCLUDED'
    for w in c['bandwidth']['windows']:
        if w['region']=='internal':assert w['normal_records']==w['records'] and w['bandwidth_min_hz']>=95000000
training=root/'training.json';gain=json.loads(training.read_text())['gain']
cases=[]
for m in ('qpsk','qam16'):
    cases.append(spec(212100,m,gain,10))
    cases.append(spec(212100,m,gain,60,('hann',)))
cases.append(spec(212100,'qpsk',gain,300,('hann',)))
prepare(cases,root/'continuous',training)
