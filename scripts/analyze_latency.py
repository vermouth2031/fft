"""Validate and summarize simulator-edge latency events on a common ns timebase."""
import argparse
import csv
import json
from pathlib import Path
import statistics
from record_build_stage import sha


def analyze(path):
    groups={}
    for row in csv.DictReader(Path(path).open()):
        key=(int(row['case']),int(row['window']))
        events=groups.setdefault(key,{})
        if row['event'] in events:raise ValueError('Duplicate latency event')
        events[row['event']]=float(row['time_ns'])
    expected={'input_first','input_last','fft_first','fft_last','bank_ready','scan_first','scan_last','scan_result','analysis_done','record_observed'}
    rows=[]
    for (case,window),events in sorted(groups.items()):
        if set(events)!=expected:raise ValueError(f'Incomplete latency events: {case}/{window}')
        if events['input_last']-events['input_first']!=81910:raise ValueError('Input accumulation interval differs')
        stages={
            'input_first_to_last_ns':events['input_last']-events['input_first'],
            'input_last_to_fft_first_ns':events['fft_first']-events['input_last'],
            'fft_output_span_ns':events['fft_last']-events['fft_first'],
            'fft_last_to_bank_ns':events['bank_ready']-events['fft_last'],
            'bank_to_scan_ns':events['scan_first']-events['bank_ready'],
            'scan_first_to_last_ns':events['scan_last']-events['scan_first'],
            'scan_last_to_result_ns':events['scan_result']-events['scan_last'],
            'scan_result_to_analysis_ns':events['analysis_done']-events['scan_result'],
            'analysis_to_observed_ns':events['record_observed']-events['analysis_done']}
        total=events['analysis_done']-events['input_first']
        if total>2000000 or any(x<0 for x in stages.values()):raise ValueError('Latency order or deadline failed')
        if sum(stages.values())!=events['record_observed']-events['input_first']:raise ValueError('Stage decomposition does not sum')
        rows.append(dict(case=case,window=window,analysis_ns=total,**stages))
    if len(rows)!=64:raise ValueError('Expected all 64 legacy windows')
    summary={name:dict(min=min(r[name] for r in rows),median=statistics.median(r[name] for r in rows),
                      max=max(r[name] for r in rows)) for name in rows[0] if name not in ('case','window')}
    return dict(status='PASS',timebase='simulation real time, ns; 100MHz source and 125MHz FFT',
        accumulation_definition='last accepted edge minus first = 81910ns; inclusive 8192-sample duration = 81920ns',
        publication_definition='record_observed is the core consumer edge, not the peripheral ring commit or PC/UDP latency',
        scan_implementation='eight-lane' if summary['scan_first_to_last_ns']['max']<10000 else 'four-lane' if summary['scan_first_to_last_ns']['max']<20000 else 'two-lane',
        scope='Measured RTL simulator stages; physical board performance requires separate capture evidence',
        input_sha256=sha(Path(path)),summary=summary,windows=rows)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('events',type=Path);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    result=analyze(args.events);args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('LATENCY_DECOMPOSITION_PASS',result['summary']['analysis_ns'])
