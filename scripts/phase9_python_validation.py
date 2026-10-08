"""Run and bind host/oracle regressions to the current Phase 9 source files."""
import datetime,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TESTS=('check_host.py','test_host_protocol.py','test_frame_length_reference.py',
       'test_detector_host.py','test_phase9_ofdm.py','check_sd_parser.py','test_qualification.py')


def main():
    folder=ROOT/'build/logs/python';folder.mkdir(parents=True,exist_ok=True)
    report=dict(status='RUNNING',tests=[],started_at=datetime.datetime.now().astimezone().isoformat())
    for test in TESTS:
        result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tests'/test)],cwd=ROOT,
                              capture_output=True,text=True,encoding='utf-8')
        log=folder/(test+'.log');log.write_text(result.stdout+result.stderr,encoding='utf-8')
        report['tests'].append(dict(script=test,exit_code=result.returncode,
                                   log=str(log.relative_to(ROOT)),sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
        print(test,'PASS' if result.returncode==0 else 'FAIL',flush=True)
        if result.returncode:
            print(result.stdout+result.stderr);report['status']='FAIL';break
    else:report['status']='PASS'
    report['finished_at']=datetime.datetime.now().astimezone().isoformat()
    report['inputs']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                      for folder_name in ('tests','host') for p in (ROOT/folder_name).glob('*.py')}
    (ROOT/'reports/phase9_python_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if report['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
