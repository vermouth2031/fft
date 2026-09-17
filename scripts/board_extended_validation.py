"""Opt-in real-board pressure, receiver-fault and host-clock validation."""
import argparse, hashlib, json, math, socket, struct, sys, time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
import iq_client as h
import numpy as np
from generate_iq_vectors import burst_reference

def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def check_bursts(folder,vector,cyclic):
    m=json.loads((folder/'capture.json').read_text());iq=np.fromfile(vector,dtype='<i2').reshape(-1,2)
    refs=burst_reference(iq);n=len(iq);count=0;cache={}
    with (folder/'burst.bin').open('rb') as stream:
        for offset in range(0,m['input_samples'],n):
            for r in refs:
                start=offset+r['start'];end=min(offset+r.get('end_exclusive',n),m['input_samples'])
                if start>=m['input_samples']:continue
                a=h.decode_record(stream.read(64),'burst');assert a['id']==count and a['sequence']==count
                assert (a['start_sample'],a['end_sample_exclusive'],a['length_samples'])==(start,end,end-start)
                key=(r['start'],end-start)
                if key not in cache:
                    x=iq[key[0]:key[0]+key[1]].astype(np.int64);p=x[:,0]**2+x[:,1]**2
                    energy=int(p.sum());cache[key]=(energy,math.isqrt(int(p.max())<<32),math.isqrt((energy<<32)//len(p)))
                energy,peak,rms=cache[key]
                assert (a['raw_energy'],a['peak_codes']*65536,a['rms_codes']*65536)==(energy,peak,rms)
                partial=not r['complete'] or offset+r.get('end_exclusive',n)>m['input_samples']
                assert a['flags_raw']==(256 if partial else 0)
                count+=1
            if not cyclic:break
        assert not stream.read(1)
    assert count==m['burst_records']
    return {'exact_burst_records':count,'burst_rate_per_nominal_second':count/(m['input_samples']/1e8)}

class ImpairedSocket:
    def __init__(self,inner,mode):self.inner=inner;self.mode=mode;self.streams=0;self.dropped=0;self.triggered=False;self.started=None
    def __getattr__(self,name):return getattr(self.inner,name)
    def recv(self,n):
        while True:
            packet=self.inner.recv(n);kind=struct.unpack_from('<I',packet,4)[0]
            if kind in (0x100,0x101):
                self.streams+=1
                if self.streams==200 and not self.triggered:
                    self.triggered=True;self.started=time.monotonic()
                    if self.mode=='pause_receiver':
                        # Stop socket reads so the bounded OS receive buffer overflows.
                        time.sleep(.7)
                    if self.mode=='drop_one':self.dropped+=1;continue
                if self.mode=='blackhole' and self.started is not None and time.monotonic()-self.started<.5:
                    self.dropped+=1;continue
            if self.mode=='drop_start_reply' and kind==0x80000002 and not self.triggered:
                self.triggered=True;self.dropped+=1;continue
            return packet

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out
    out.mkdir(parents=True,exist_ok=False);(out/'vectors').mkdir();results=[]
    def capture(name,vector,seconds=0,mode=None):
        folder=out/name;original=h.Client;created=[]
        if mode:
            class FaultClient(original):
                def __init__(self,*args,**kwargs):
                    super().__init__(*args,**kwargs)
                    if mode=='pause_receiver':self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,32768)
                    self.sock=ImpairedSocket(self.sock,mode);created.append(self)
            h.Client=FaultClient
        error=None
        try:
            h.capture(SimpleNamespace(board='192.168.1.10',port=5001,vector=str(vector),out=str(folder),window='hann',cyclic=seconds>0,seconds=seconds or 1))
        except RuntimeError as exc:error=str(exc)
        finally:h.Client=original
        m=json.loads((folder/'capture.json').read_text())
        row={'name':name,'metadata':m,'exception':error}
        if mode:
            shim=created[0].sock;row.update(injection=mode,injected=shim.triggered,discarded_by_shim=shim.dropped)
            assert shim.triggered
            if mode!='drop_start_reply':
                assert error and not m['capture_complete'] and m['frequency_records_missing']+m['burst_records_missing']>0
                row['status']='EXPECTED_LOSS_DETECTED'
            else:
                assert not error and m['capture_complete'];row['status']='RETRY_PASS'
        else:assert not error and m['capture_complete'];row['status']='PASS'
        results.append(row);save(out/'progress.json',results);return folder,row
    tone=ROOT/'data/vectors/tone_pos_fs4.bin';qpsk=ROOT/'data/vectors/qpsk_sps4.bin'
    for length in (64,512,4096):
        iq=np.zeros((32768,2),dtype='<i2');start=8192-length//2
        for k in range(start,start+length):iq[k]=(8192,0) if k%4==0 else (0,8192) if k%4==1 else (-8192,0) if k%4==2 else (0,-8192)
        v=out/'vectors'/f'short_{length}.bin';iq.tofile(v)
        folder,row=capture(f'short_{length}',v);row.update(check_bursts(folder,v,False))
    iq=np.fromfile(tone,dtype='<i2').reshape(-1,2).copy()
    iq//=2;v=out/'vectors/tone_half.bin';iq.tofile(v)
    folder,row=capture('half_amplitude',v)
    fr=json.loads((folder/'frequency.json').read_text());assert all(r['rms_codes']==4096 and r['peak_codes']==4096 and r['peak_hz']==25000000 for r in fr)
    iq=np.zeros((32768,2),dtype='<i2')
    for start in (2048,18432):
        for k in range(start,start+4096):iq[k]=(8192,0) if k%4==0 else (0,8192) if k%4==1 else (-8192,0) if k%4==2 else (0,-8192)
    v=out/'vectors/pressure_two_bursts.bin';iq.tofile(v)
    folder,row=capture('pressure_20s',v,20);row.update(check_bursts(folder,v,True))
    assert row['burst_rate_per_nominal_second']>5000
    for mode in ('drop_one','blackhole','pause_receiver','drop_start_reply'):
        capture(mode,qpsk,2,mode)
        capture(mode+'_recovery',tone)
    # Independent PC performance counter, with network-latency bounds for every hardware latch.
    c=h.Client('192.168.1.10')
    def sample():
        lo=time.perf_counter_ns();c.request(5,[0]);w=c.read(0x110,2);hi=time.perf_counter_ns()
        return {'host_lo_ns':lo,'host_hi_ns':hi,'ticks':w[0]|w[1]<<32}
    try:
        first=min((sample() for _ in range(8)),key=lambda x:x['host_hi_ns']-x['host_lo_ns'])
        time.sleep(10)
        last=min((sample() for _ in range(8)),key=lambda x:x['host_hi_ns']-x['host_lo_ns'])
        delta=last['ticks']-first['ticks'];minimum=delta*1e9/(last['host_hi_ns']-first['host_lo_ns']);maximum=delta*1e9/(last['host_lo_ns']-first['host_hi_ns'])
        clock={'method':'PC perf_counter_ns versus FPGA source_ticks; bounds include both network latch intervals',
               'first':first,'last':last,'source_clock_hz_lower_bound':minimum,'source_clock_hz_upper_bound':maximum,
               'midpoint_hz':(minimum+maximum)/2,'metrology_calibrated':False}
        assert 99e6<minimum<=maximum<101e6
        save(out/'host_clock_comparison.json',clock)
        assert c.read(8)[0]&7==0 and c.read(0x60)[0]==0
    finally:c.close()
    report={'status':'PASS','source':'Real Zybo Z7-20 UDP hardware, synthetic receiver faults explicitly labelled',
            'cases':results,'host_clock_comparison':clock,'physical_cable_unplug_test':False}
    save(out/'extended_validation.json',report);print('EXTENDED_BOARD_PASS',out,flush=True)
if __name__=='__main__':main()
