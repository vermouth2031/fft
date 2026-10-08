"""Verify the enlarged FFT on a matching, timing-passed RAM/JTAG or boot image.

This is separate from old release acceptance, whose 8K fixtures are historical.
Every result is checked against the AMD integer oracle and capture conservation.
"""
import argparse,contextlib,datetime,json,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
from iq_client import Client,decode_record
from phase4_identity import check_identity
from package_release import check as check_build
from qualification_capture import capture
from validate_measurements import load_index,check_bindings,error_rows,summarize,write_errors,configuration,verify_configuration
from verify_board_capture import verify,digest
from detection_metrics import evaluate


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--board',default='192.168.1.10');p.add_argument('--source-ip',default='192.168.1.20')
    a=p.parse_args();index=load_index(a.references);check_build()
    client=Client(a.board,source_ip=a.source_ip)
    try:
        hardware=client.hardware_info();check_identity(hardware)
        if client.read(8)[0]&7:raise RuntimeError('Board is running another acquisition')
    finally:client.close()
    a.out.mkdir(parents=True,exist_ok=False)
    report=dict(status='RUNNING',hardware=hardware,started_at=datetime.datetime.now().astimezone().isoformat(),
                scope='Finite numerical and integrity acceptance; cold power-cycle validation is separate',
                references=str(a.references.resolve()),references_sha256=digest(a.references),cases=[],
                artifacts={name:digest(ROOT/'artifacts'/name) for name in ('iq_analyzer.bit','iq_udp.elf')})
    rows=[]
    try:
        for row in index['cases']:
            label=row['label'];case=row['case'];folder=a.out/label
            reference=a.references.parent/row['reference'];oracle=json.loads(reference.read_text())
            print('PHASE9_CASE_START',label,flush=True)
            with (a.out/(label+'.log')).open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log):
                capture(SimpleNamespace(board=a.board,port=5001,source_ip=a.source_ip,vector=row['vector'],
                    out=str(folder),window=oracle['mode'],cyclic=False,seconds=1,
                    detector=case['applied_detector']['mode'],gap_min=case['applied_detector']['gap_min']),case['applied_detector'])
            save(folder/'configuration.json',configuration(a.board,5001))
            verify_configuration(folder,case,oracle['mode'])
            result=verify(folder,row['vector'],qualification=reference)
            if result['maximum_analysis_us']>350 or result['maximum_publish_us']>360:
                raise AssertionError('Phase 9 latency target exceeded')
            raw=(folder/'burst.bin').read_bytes();intervals=[]
            for i in range(0,len(raw),64):
                burst=decode_record(raw[i:i+64],'burst')
                intervals.append([burst['start_sample'],burst['end_sample_exclusive']])
            result.update(label=label,detection_metrics=evaluate(case['measurement_design']['truth_intervals'],intervals,case['samples']))
            save(folder/'measurement_validation.json',result)
            report['cases'].append(result);rows.extend(error_rows(folder,case,oracle))
            save(a.out/'validation.json',report)
        check_bindings(index['bindings'])
        report.update(status='PASS',summary=summarize(rows),
                      frequency_records=sum(c['frequency_records'] for c in report['cases']),
                      burst_records=sum(c['burst_records'] for c in report['cases']),
                      maximum_analysis_us=max(c['maximum_analysis_us'] for c in report['cases']),
                      maximum_publish_us=max(c['maximum_publish_us'] for c in report['cases']))
    except Exception as error:
        report.update(status='FAIL',error=str(error));raise
    finally:
        report['finished_at']=datetime.datetime.now().astimezone().isoformat()
        write_errors(a.out,rows);save(a.out/'validation.json',report)
    print('PHASE9_NUMERICAL_BOARD_PASS',len(report['cases']))


if __name__=='__main__':main()
