"""Generate IQ blocks on the PC while the FPGA analyzes the other ping-pong bank."""
from __future__ import annotations
import argparse,json,math,random,struct,time
from pathlib import Path
from iq_client import Client,STREAM_VERSION,decode_record,export

RATE=125_000_000
SIGNALS=('single','dual','chirp','qpsk','ofdm','noise')

def clip(value):return max(-32768,min(32767,int(round(value))))

def make_signal(kind,count,block_id,custom=None):
    if custom is not None:
        data=Path(custom).read_bytes()
        if len(data)!=count*4:raise ValueError(f'Custom IQ file must be exactly {count*4} bytes')
        return data
    rng=random.Random(0x49510000+block_id);out=[]
    qpsk=[(1,1),(1,-1),(-1,1),(-1,-1)]
    ofdm_bins=[-1500,-1200,-901,-600,-301,-151,151,301,600,901,1200,1500]
    ofdm_symbols=[qpsk[rng.randrange(4)] for _ in ofdm_bins]
    for n in range(count):
        if kind=='single':
            phase=2*math.pi*997*n/8192;i=15000*math.cos(phase);q=15000*math.sin(phase)
        elif kind=='dual':
            p1=2*math.pi*701*n/8192;p2=2*math.pi*(-1301)*n/8192
            i=8500*(math.cos(p1)+math.cos(p2));q=8500*(math.sin(p1)+math.sin(p2))
        elif kind=='chirp':
            m=n%8192;phase=2*math.pi*(-1800*m/8192+3600*m*m/(2*8192*8192))
            i=14500*math.cos(phase);q=14500*math.sin(phase)
        elif kind=='qpsk':
            si,sq=qpsk[(n//16+block_id)%4];i=12000*si;q=12000*sq
        elif kind=='ofdm':
            m=n%8192;i=q=0.0
            for b,(si,sq) in zip(ofdm_bins,ofdm_symbols):
                phase=2*math.pi*b*m/8192;c=math.cos(phase);s=math.sin(phase)
                i+=si*c-sq*s;q+=si*s+sq*c
            i*=1100;q*=1100
        elif kind=='noise':i=rng.gauss(0,5000);q=rng.gauss(0,5000)
        else:raise ValueError(f'Unknown signal {kind}')
        out.append(struct.pack('<hh',clip(i),clip(q)))
    return b''.join(out)

def wait_for_block(client,block_id,timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        status=client.stream_status()
        if status['current_block_id']==block_id and not status['pending_valid']:return status
    raise TimeoutError(f'FPGA did not activate block {block_id}')

def run(args):
    client=Client(args.board,args.port);started=False
    report=dict(board=args.board,requested_blocks=args.blocks,samples_per_block=args.samples,
        sample_rate_hz=RATE,semantics='PC updates the inactive bank while FPGA replays the active bank at 125 MSPS')
    try:
        info=client.hardware_info()
        if info['hardware_version']<STREAM_VERSION or not info['hardware_capabilities']&4:
            raise RuntimeError('Phase 7 or newer streaming BOOT.BIN is required')
        config=[args.samples,1,1,0,8191,1048576,0,262144,0,8,32,1048576,0]
        client.configure(config,hardware=info)
        kinds=[args.signal] if args.signal else list(SIGNALS)
        first_kind=kinds[0];first=make_signal(first_kind,args.samples,1,args.custom)
        crc,status=client.upload_stream_block(first,0,1,arm=True)
        client.control(1);started=True
        activated=[];upload_seconds=[]
        for index in range(2,args.blocks+1):
            status=client.stream_status();bank=1-status['active_bank'];kind=kinds[(index-1)%len(kinds)]
            data=make_signal(kind,args.samples,index,args.custom);begin=time.monotonic()
            crc,status=client.upload_stream_block(data,bank,index,arm=True,
                progress=(lambda done,total:print(f'\rblock {index} bank {bank}: {done}/{total} samples',end='',flush=True)) if args.progress else None)
            upload_seconds.append(time.monotonic()-begin)
            status=wait_for_block(client,index,args.switch_timeout)
            activated.append(dict(block_id=index,signal=kind,bank=bank,crc32=f'{crc:08x}',switch_count=status['switch_count']))
            if args.progress:print()
        end=time.monotonic()+args.hold
        while time.monotonic()<end:
            try:client.receive()
            except TimeoutError:pass
            except OSError:pass
            except Exception as error:
                import socket
                if not isinstance(error,socket.timeout):raise
        client.control(2);started=False
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and client.read(8)[0]&7:
            try:client.receive()
            except Exception:pass
        status=client.stream_status()
        report.update(hardware=info,activated=activated,final_status=status,
            upload_seconds=upload_seconds,average_upload_mbps=(args.samples*32/1e6)/(sum(upload_seconds)/len(upload_seconds)) if upload_seconds else None,
            frequency_records=len(client.frequency),burst_records=len(client.bursts),status='PASS')
        export(args.out,client.frequency,client.bursts,report)
    except Exception as error:
        report.update(status='FAIL',failure_reason=str(error));raise
    finally:
        if started:
            try:client.control(2)
            except Exception:pass
        Path(args.out).mkdir(parents=True,exist_ok=True)
        (Path(args.out)/'streaming.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        client.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board',default='192.168.1.10');p.add_argument('--port',type=int,default=5001)
    p.add_argument('--signal',choices=SIGNALS);p.add_argument('--custom',type=Path)
    p.add_argument('--samples',type=int,choices=(8192,16384,24576,32768),default=32768)
    p.add_argument('--blocks',type=int,default=12);p.add_argument('--hold',type=float,default=1.0)
    p.add_argument('--switch-timeout',type=float,default=5);p.add_argument('--progress',action='store_true')
    p.add_argument('--out',type=Path,default=Path('captures/streaming'))
    args=p.parse_args()
    if args.blocks<2:p.error('--blocks must be at least 2')
    if args.custom and args.signal:p.error('use either --custom or --signal')
    run(args)
if __name__=='__main__':main()
