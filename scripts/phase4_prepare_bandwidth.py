"""Freeze OFDM training gain and new exact reference matrices without touching baseline tools."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from phase4_ofdm import ROOT,FS,N,make_case,waveform,float_spectrum
from fft_reference import FFTReference,digest
from validate_measurements import bindings,check_bindings,read,save,require


def sources():
    value=bindings()
    for name in ('phase4_ofdm.py','phase4_test_ofdm.py','phase4_prepare_bandwidth.py','phase4_validate_bandwidth.py'):
        p=ROOT/'scripts'/name;value[str(p)]=digest(p)
    return value


def prepare(cases,out,training_path):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    vectors=out/'vectors';vectors.mkdir();references=out/'references';references.mkdir()
    source=sources();source[str(training_path.resolve())]=digest(training_path)
    manifest=dict(schema='iq-phase4-ofdm-manifest-v1',bindings=source,cases=[])
    for case in cases:
        floating,iq,details=waveform(case)
        vector=vectors/(case['id']+'.bin');vector.write_bytes(iq.tobytes())
        manifest['cases'].append(dict(spec=case,details=details,vector=str(vector),sha256=digest(vector)))
    manifest_path=out/'manifest.json';save(manifest_path,manifest)
    source=dict(source);source[str(manifest_path)]=digest(manifest_path)
    index=dict(schema='iq-phase4-ofdm-index-v1',manifest=str(manifest_path),bindings=source,cases=[])
    with FFTReference() as model:
        source[model.identity['archive_path']]=model.identity['archive_sha256']
        source[model.identity['dll_path']]=model.identity['dll_sha256']
        index['model']=model.identity
        for row in manifest['cases']:
            case=row['spec'];floating,iq,details=waveform(case)
            for mode in case['windows']:
                label=case['id']+'_'+mode
                oracle=dict(schema='iq-qualification-reference-v1',case_id=case['id'],mode=mode,
                    input_sha256=row['sha256'],sample_rate_hz=FS,detector=case['detector'],
                    replay=case['replay'],bindings=source,model=model.identity,windows=[],snapshots=[],algorithm=[])
                for wid in range(4):
                    raw=iq[wid*N:(wid+1)*N].astype(np.int64)
                    expected,_,snapshot=model.window(raw,mode,wid)
                    oracle['windows'].append(expected);oracle['snapshots'].append(snapshot.tolist())
                    coeff=model.hann/131072 if mode=='hann' else np.ones(N)
                    oracle['algorithm'].append(dict(float_spectrum(raw,coeff),**details['windows'][wid]))
                path=references/(label+'.json');save(path,oracle)
                index['cases'].append(dict(label=label,case=case,details=details,vector=row['vector'],
                    reference=str(path),reference_sha256=digest(path)))
    check_bindings(source);save(out/'index.json',index)
    print('PHASE4_REFERENCES_READY',out,len(index['cases']),flush=True)


def load_index(path):
    index=read(path);require(index['schema']=='iq-phase4-ofdm-index-v1','Wrong OFDM index')
    check_bindings(index['bindings']);manifest=read(index['manifest']);check_bindings(manifest['bindings'])
    expected=[]
    for row in manifest['cases']:
        _,iq,details=waveform(row['spec']);vector=Path(row['vector'])
        require(vector.read_bytes()==iq.tobytes() and digest(vector)==row['sha256'],'OFDM waveform changed')
        require(details==row['details'],'OFDM design metadata changed')
        expected.extend((row,w) for w in row['spec']['windows'])
    require(len(index['cases'])==len(expected),'OFDM matrix incomplete')
    for item,(row,mode) in zip(index['cases'],expected):
        require(item['case']==row['spec'] and item['details']==row['details'] and item['vector']==row['vector'],'OFDM mapping changed')
        require(item['label']==row['spec']['id']+'_'+mode,'OFDM label changed')
        oracle=read(item['reference'])
        require(digest(item['reference'])==item['reference_sha256'],'Oracle changed')
        require(oracle['bindings']==index['bindings'] and oracle['model']==index['model'],'Oracle source binding changed')
        require(oracle['input_sha256']==row['sha256'] and oracle['mode']==mode and oracle['detector']==row['spec']['detector'],'Oracle metadata mismatch')
    return index


def train(out):
    rows=[]
    for seed in range(210000,210100):
        for band in (85,90,95):
            for modulation in ('qpsk','qam16'):
                c=make_case(band,modulation,seed,gain=1)
                x,_,_=waveform(c)
                rows.append(dict(seed=seed,band=band,modulation=modulation,
                    component_peak=float(max(abs(x.real).max(),abs(x.imag).max()))))
    peak=max(r['component_peak'] for r in rows)
    gain=min(6000,int(.70*32767/peak))
    report=dict(status='FROZEN',policy='One common gain chosen from 600 training inputs only; at most 6000, at most 70% int16 training peak',
        gain=gain,training_seeds=[210000,210099],validation_seeds=[211000,211019],
        boundary_seeds=[211100,211102],source_sha256=digest(ROOT/'scripts/phase4_ofdm.py'),rows=rows)
    save(out/'training.json',report);return gain


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    gain=train(a.out);cases=[]
    for band in (85,90,95):
        for modulation in ('qpsk','qam16'):
            for seed in range(211000,211020):cases.append(make_case(band,modulation,seed,gain=gain))
    prepare(cases,a.out/'finite',a.out/'training.json')
    boundary=[make_case(95,m,s,gain=gain,carrier_hz=f,windows=('hann',),boundary=True)
        for m in ('qpsk','qam16') for s in range(211100,211103) for f in (0,1000000,2000000,4000000)]
    prepare(boundary,a.out/'boundary',a.out/'training.json')


if __name__=='__main__':main()
