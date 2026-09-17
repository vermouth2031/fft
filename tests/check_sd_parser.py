"""Exercise SD file parsing with genuine RTL output, explicitly labelled simulation."""
from pathlib import Path
import json,struct,tempfile,sys,contextlib,io
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
from analyze_sd import analyze
cases=[{'F':[],'B':[]} for _ in range(16)]
for line in (ROOT/'build/vivado/iq_analyzer.sim/sim_1/behav/xsim/core_results.txt').read_text().splitlines():
    kind,c,*values=line.split();w=[int(x,16) for x in values]
    cases[int(c)][kind].append(struct.pack('<'+'I'*len(w),*w))
with tempfile.TemporaryDirectory(prefix='iq_sd_parser_') as temp:
    base=Path(temp);run=base/'simulation';out=base/'decoded'
    for c,records in enumerate(cases):
        d=run/f'C{c:02d}';d.mkdir(parents=True)
        (d/'FREQ.BIN').write_bytes(b''.join(records['F']));(d/'BURST.BIN').write_bytes(b''.join(records['B']))
        (d/'META.JSON').write_text(json.dumps(dict(source='RTL simulation parser fixture',
            capture_complete=True,error_status=0,input_samples=32768,epoch=1,config_id=1)))
    with contextlib.redirect_stdout(io.StringIO()):analyze(run,out,simulation_fixture=True)
    report=json.loads((out/'board_validation.json').read_text());assert not report['board_tested']
    assert report['status']=='PASS' and len(report['cases'])==16
print('SD_PARSER_SIMULATION_PASS 16 cases; no physical board data used')
