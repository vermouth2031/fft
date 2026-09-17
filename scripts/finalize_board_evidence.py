"""Consolidate observed board evidence; never manufacture missing test results."""
from pathlib import Path
import datetime,hashlib,json,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
from iq_client import Client,decode_record
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
out=ROOT/'captures/extended_20260917'
extended=load(out/'extended_validation.json');assert extended['status']=='PASS'
link=load(out/'link_interrupt_fixed/link_recovery.json');assert link['status']=='PASS' and not link['jtag_intervention']
gui=load(out/'gui/gui_validation.json');assert gui['status']=='PASS'
uart=(out/'uart_startup.log').read_text();assert 'IQ analyzer: UDP 5001' in uart and 'Board IP: 192.168.1.10' in uart and 'link speed for phy address 1: 1000' in uart
assert 'CAPTURE_PASS' in (out/'jtag_finite_fixed.log').read_text(encoding='utf-8-sig')
gold=load(ROOT/'data/golden_results.json')['cases'][9]
raw=(out/'jtag_finite/frequency.bin').read_bytes();assert len(raw)==512
mapping={'total_spectrum_power':'total','peak_spectrum_power':'peak_power','peak_hz':'f_peak_hz',
         'low_hz':'f_low_hz','high_hz':'f_high_hz','bandwidth_hz':'bandwidth_hz','bandcenter_hz':'center_hz','raw_energy':'energy'}
for n in range(4):
    a=decode_record(raw[n*128:(n+1)*128],'frequency');e=gold['windows'][n]
    for target,source in mapping.items():assert a[target]==e[source]
    assert a['peak_codes']==8192 and a['rms_codes']==8192 and a['flags_raw']==0
b=decode_record((out/'jtag_finite/burst.bin').read_bytes(),'burst')
assert b['length_samples']==32768 and b['rms_codes']==8192 and b['flags_raw']==256
assert (out/'jtag_finite/replay_readback.bin').read_bytes()==(ROOT/'data/vectors/tone_pos_fs4.bin').read_bytes()
c=Client('192.168.1.10')
try:
    state={'magic':hex(c.read(0)[0]),'status':c.read(8)[0],'error_status':c.read(0x60)[0],'epoch':c.read(0x68)[0]}
    assert state['magic']=='0x49514131' and state['status']&7==0 and state['error_status']==0
finally:c.close()
save(out/'final_board_state.json',state)
regressions=[]
for script,args in [('tests/check_host.py',[]),('tests/test_host_protocol.py',[]),('scripts/package_release.py',['--check'])]:
    result=subprocess.run([sys.executable,str(ROOT/script),*args],capture_output=True,text=True,encoding='utf-8',errors='replace')
    regressions.append({'script':script,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    assert result.returncode==0,regressions[-1]
save(ROOT/'reports/host_regression_final.json',{'status':'PASS','checks':regressions})
report={'status':'PASS','verified_at':datetime.datetime.now().astimezone().isoformat(),
        'extended_cases':extended['cases'],'host_clock_comparison':extended['host_clock_comparison'],
        'link_recovery':link,'gui':gui,'uart':load(out/'uart_capture.json'),
        'jtag_finite':{'status':'PASS','frequency_records':4,'burst_records':1,'replay_readback':True,'integer_measurements_match':True},
        'display_snapshots':load(ROOT/'reports/board_snapshot_validation.json'),
        'final_board_state':state,'final_boot_mode':'SD, after system reset',
        'initial_link_failure_preserved':'captures/extended_20260917/link_interrupt/link_recovery.json',
        'initial_jtag_failure_preserved':'captures/extended_20260917/jtag_reload.log',
        'not_completed':['calibrated-instrument absolute clock measurement','PCB/power-label physical inspection'],
        'optional_extensions_not_implemented':['125 MSPS','external ADC','custom FFT'],
        'verified_sources':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ('host/iq_client.py','host/monitor.py','scripts/program_board.tcl','scripts/jtag_capture.tcl')}}
save(ROOT/'reports/board_validation_extended.json',report)
print('FINAL_BOARD_EVIDENCE_PASS',json.dumps(state))
if __name__=='__main__':pass
