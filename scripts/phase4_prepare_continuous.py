"""Apply the predeclared group-wide selection rule, never select a lucky seed."""
import argparse
from pathlib import Path
import json
from phase4_prepare_bandwidth import prepare
from phase4_ofdm import make_case

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--finite',type=Path,required=True)
    a=p.parse_args();result=json.loads(a.finite.read_text());assert result['status']=='PASS' and len(result['cases'])==240
    # Both complete b95 groups must pass before either is exposed for demo.
    for modulation in ('qpsk','qam16'):
        group=[r for r in result['cases'] if f'b95_{modulation}_' in r['label']]
        assert len(group)==40 and all(r['bandwidth']['all_internal_windows_at_least_90mhz'] for r in group)
    train=a.root/'training.json';gain=json.loads(train.read_text())['gain'];cases=[]
    for modulation in ('qpsk','qam16'):
        cases.append(make_case(95,modulation,211000,gain=gain,seconds=10))
        cases.append(make_case(95,modulation,211000,gain=gain,seconds=60,windows=('hann',)))
    cases.append(make_case(95,'qpsk',211000,gain=gain,seconds=300,windows=('hann',)))
    prepare(cases,a.root/'continuous',train)

if __name__=='__main__':main()
