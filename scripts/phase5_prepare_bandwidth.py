"""New physical OFDM holdout, entered only after 125 MSPS continuous service."""
import argparse
import json
from pathlib import Path
import numpy as np
from phase4_ofdm import ROOT, FS, make_case, waveform
from phase4_prepare_bandwidth import prepare, save
from fft_reference import digest
from phase4_identity import check_identity


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--throughput-report',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve()
    assert out.is_relative_to(ROOT/'build') and FS==125000000
    service=json.loads(a.throughput_report.read_text())
    assert service['status']=='PASS' and service['hardware']['sample_rate_hz']==FS
    check_identity(service['hardware'])
    assert sorted(r['seconds'] for r in service['cases'])==[10,60,300]
    assert service['maximum_fifo_high_water']<1024
    out.mkdir(parents=True,exist_ok=False)
    spec=dict(status='FROZEN_BEFORE_VALIDATION',sample_rate_hz=FS,
              design_spans_mhz=[110,118,122],modulations=['qpsk','qam16'],windows=['rect','hann'],
              training_seeds=list(range(310600,310620)),holdout_seeds=list(range(311300,311320)),
              boundary_seeds=[311400,311401,311402],boundary_carriers_hz=[-2000000,0,1000000,2000000],
              primary_span_mhz=118,target_minimum_internal_99pct_obw_hz=115000000,
              continuous_seed=311300,continuous_scope='Repeated RAM input; not new independent samples',
              throughput_evidence_sha256=digest(a.throughput_report),source_sha256=digest(Path(__file__)))
    save(out/'specification.json',spec)
    peaks=[]
    for seed in spec['training_seeds']:
        for band in spec['design_spans_mhz']:
            for modulation in spec['modulations']:
                x,_,_=waveform(make_case(band,modulation,seed,gain=1))
                peaks.append(float(max(np.abs(x.real).max(),np.abs(x.imag).max())))
    gain=min(6000,int(.70*32767/max(peaks)))
    training=dict(status='FROZEN',gain=gain,component_peaks=peaks,
                  policy='Common gain <=6000 and <=70% of training component full scale; holdout never retuned',
                  specification_sha256=digest(out/'specification.json'))
    save(out/'training.json',training)
    finite=[make_case(b,m,s,gain=gain) for b in spec['design_spans_mhz']
            for m in spec['modulations'] for s in spec['holdout_seeds']]
    prepare(finite,out/'finite',out/'training.json')
    boundary=[make_case(122,m,s,gain=gain,carrier_hz=f,windows=('hann',),boundary=True)
              for m in spec['modulations'] for s in spec['boundary_seeds'] for f in spec['boundary_carriers_hz']]
    prepare(boundary,out/'boundary',out/'training.json')
    print('PHASE5_BANDWIDTH_REFERENCES_READY finite=240 boundary=24',flush=True)


if __name__=='__main__':main()
