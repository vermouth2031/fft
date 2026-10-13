"""Run the complete 64-window AMD RTL regression in isolated case groups."""
import concurrent.futures,hashlib,json,os,shutil,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'build/vivado16k/iq_analyzer.sim/sim_1/behav/xsim'
VIVADO=Path(os.environ.get('VIVADO_ROOT',r'D:\VivadoMM\2026.1\Vivado'))/'bin'


def main():
    logs=ROOT/'build/logs';logs.mkdir(parents=True,exist_ok=True)
    compile_log=logs/'sim_core_compile.log'
    command=[str(VIVADO/'vivado.bat'),'-mode','batch','-notrace','-nojournal','-log',str(compile_log),
             '-source',str(ROOT/'scripts/sim_core.tcl'),'-tclargs','compile_only']
    with (logs/'sim_core_compile_console.log').open('w',encoding='utf-8') as output:
        subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,check=True)
    parent=ROOT/'build/core_parallel';parent.mkdir(parents=True,exist_ok=True)
    # Unique run directories preserve every attempt and avoid sharing simulator state.
    import datetime
    run=parent/datetime.datetime.now().strftime('%Y%m%d_%H%M%S');run.mkdir()
    condition=threading.Condition();active=[0]
    hardware_lock=Path(os.environ['IQ_CORE_HARDWARE_LOCK']) if os.environ.get('IQ_CORE_HARDWARE_LOCK') else None
    def worker(first):
        with condition:
            while active[0] >= (min(2,workers) if hardware_lock and hardware_lock.exists() else workers):
                condition.wait(timeout=2)
            active[0]+=1
        try:return run_group(first)
        finally:
            with condition:
                active[0]-=1;condition.notify_all()
    def run_group(first):
        out=run/f'cases_{first:02d}_{first+1:02d}';out.mkdir()
        for name in ('test_iq.mem','golden_fft.mem','hann_quarter_u18_f17.mem'):
            shutil.copyfile(SIM/name,out/name)
        shutil.copytree(SIM/'xsim.dir',out/'xsim.dir')
        # Batch wrappers split unquoted equals signs; pass plusargs in a file.
        (out/'xsim.args').write_text(f'-R\n-onerror quit\n-testplusarg CASE_START={first}\n-testplusarg CASE_END={first+2}\n-log simulate.log\n')
        cmd=[str(VIVADO/'xsim.bat'),'tb_core_behav','-f','xsim.args']
        with (out/'console.log').open('w',encoding='utf-8') as output:
            result=subprocess.run(cmd,cwd=out,stdout=output,stderr=subprocess.STDOUT)
        text=(out/'simulate.log').read_text(encoding='utf-8',errors='replace') if (out/'simulate.log').exists() else (out/'console.log').read_text(encoding='utf-8',errors='replace')
        if result.returncode or 'CORE_PASS cases=2' not in text or 'Fatal:' in text or 'FFT_MISMATCH' in text:
            raise RuntimeError(f'Core regression failed: {out}')
        print(f'CORE_GROUP_PASS cases={first}..{first+1}',flush=True)
        return first,out,text
    results=[]
    # Bound peak memory when Vivado synthesis runs alongside the AMD model.
    # All eight groups still execute; only their concurrency changes.
    workers=int(os.environ.get('IQ_CORE_WORKERS','2'))
    if workers not in (1,2,3,4):raise ValueError('IQ_CORE_WORKERS must be 1..4')
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(worker,range(0,16,2)):results.append(result)
    # Publish aggregate evidence only after every group has passed.
    combined='\n'.join(text for _,_,text in results)+'\nCORE_ALL_GROUPS_PASS cases=16 windows=64\n'
    (logs/'sim_core.log').write_text(combined,encoding='utf-8')
    (SIM/'core_results.txt').write_text(''.join((out/'core_results.txt').read_text() for _,out,_ in results))
    events=['case,window,event,time_ns\n']
    for _,out,_ in results:events.extend((out/'latency_events.csv').read_text().splitlines(keepends=True)[1:])
    (SIM/'latency_events.csv').write_text(''.join(events))
    (logs/'core_parallel_manifest.json').write_text(json.dumps(dict(status='PASS',run=str(run),
        groups=[dict(first_case=first,last_case=first+1,log=str(out/'simulate.log'),
                     sha256=hashlib.sha256((out/'simulate.log').read_bytes()).hexdigest()) for first,out,_ in results]),indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'tests/check_core_results.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/analyze_latency.py'),str(SIM/'latency_events.csv'),
                    '--out',str(ROOT/'reports/phase2_latency_validation.json')],cwd=ROOT,check=True)
    print('CORE_PARALLEL_PASS all 1048576 complex outputs and 64 frequency records',flush=True)


if __name__=='__main__':main()
