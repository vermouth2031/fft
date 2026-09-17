"""Standard-library host for Zybo Z7-20 IQ analyzer; no driver or numpy needed.
python host/iq_client.py capture --vector data.bin --board 192.168.1.10 --out captures/run1
python host/iq_client.py decode --freq freq.bin --burst burst.bin --out captures/decoded
"""
from __future__ import annotations
import argparse, csv, json, random, socket, struct, time, hashlib
from pathlib import Path
MAGIC=0x49515531
FLAGS=['NO_POWER','FFT_OVERFLOW','SOURCE_GAP','PARTIAL_WINDOW','EDGE_RISK','RESOLUTION_LIMITED',
       'METADATA_ERROR','RESULT_LOSS_SEEN','CAPTURE_TRUNCATED','LENGTH_OR_COUNTER_OVERFLOW','DETECTOR_TIMEOUT','CONFIG_ABORT']
def words(data):
    if len(data)%4:raise ValueError('Word payload must be a multiple of four bytes')
    return struct.unpack('<'+'I'*(len(data)//4),data)
def signed(x):return x if x<0x80000000 else x-0x100000000
def packet_loss_count(sequences):
    if not sequences:return 0
    offsets=[((s-sequences[0]+2**31)&0xffffffff)-2**31 for s in sequences]
    return max(offsets)-min(offsets)+1-len(set(sequences))
def decode_record(data,kind):
    size=128 if kind=='frequency' else 64
    if len(data)!=size:raise ValueError(f'{kind}: expected {size} bytes')
    w=words(data);expected=0x46525131 if kind=='frequency' else 0x42525331
    if w[0]!=expected:raise ValueError(f'Unexpected record magic: {w[0]:08x}')
    u64=lambda n:w[n]|w[n+1]<<32
    out=dict(kind=kind,flags_raw=w[1],flags=[name for n,name in enumerate(FLAGS) if w[1]>>n&1],epoch=w[2],
             id=w[3],config_id=w[4],sample_rate_hz=w[5],sequence=w[-1])
    if kind=='frequency':
        out.update(first_sample=u64(6),start_tick=u64(8),done_tick=u64(10),latency_cycles=w[12],latency_us=w[12]/100,
          fft_length=w[13],peak_hz=signed(w[14]),low_hz=signed(w[15]),high_hz=signed(w[16]),bandwidth_hz=w[17],
          bandcenter_hz=signed(w[18]),q_peak=w[19]&65535,q_low=w[19]>>16,q_high=w[20]&65535,
          peak_codes=w[21]/65536,rms_codes=w[22]/65536,total_spectrum_power=u64(23),peak_spectrum_power=u64(25),
          raw_energy=u64(27),window='hann' if w[29]>>24&1 else 'rect')
    else:
        out.update(start_sample=u64(6),end_sample_exclusive=u64(8),length_samples=w[10],length_us=w[10]/(w[5]/1e6),
          peak_codes=w[11]/65536,rms_codes=w[12]/65536,raw_energy=u64(13))
    return out

class Client:
    def __init__(self,board,port=5001):
        self.remote=(board,port);self.socket_reopens=0
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024)
        self.sock.connect((board,port));self.sock.settimeout(.5)
        self.local_endpoint=self.sock.getsockname()
        self.command_sequence=random.randrange(1,2**31)
        self.frequency=[];self.bursts=[];self.packet_sequences=[]
        self._seen_packets=set();self.active_epoch=None
    def reopen_after_link_error(self,error):
        # Windows can permanently invalidate a connected UDP socket when its adapter
        # is disabled. Preserve the exact source IP/port: firmware owns this peer.
        if getattr(error,'winerror',None) not in (10022,10049,10050,10051,10052,10054,10065):raise error
        self.sock.close();deadline=time.monotonic()+12
        while True:
            replacement=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            try:
                replacement.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024)
                replacement.bind(self.local_endpoint);replacement.connect(self.remote);replacement.settimeout(.5)
                self.sock=replacement;self.socket_reopens+=1;return
            except OSError:
                replacement.close()
                if time.monotonic()>=deadline:raise error
                time.sleep(.1)
    def receive(self):
        try:packet=self.sock.recv(65535)
        except socket.timeout:raise
        except OSError as error:
            self.reopen_after_link_error(error)
            raise socket.timeout('UDP socket restored; retry the pending command')
        if len(packet)<16:raise ValueError('Short UDP packet')
        magic,kind,seq,count=struct.unpack_from('<4I',packet)
        if magic!=MAGIC:raise ValueError('Wrong UDP protocol magic')
        payload=packet[16:]
        if kind in (0x100,0x101):
            size=128 if kind==0x100 else 64
            if len(payload)!=count*size:raise ValueError('Truncated stream packet')
            accepted=[]
            for n in range(count):
                r=payload[n*size:(n+1)*size]
                decoded=decode_record(r,'frequency' if kind==0x100 else 'burst')
                if self.active_epoch is None or decoded['epoch']==self.active_epoch:accepted.append(r)
            if accepted and seq not in self._seen_packets:
                self._seen_packets.add(seq);self.packet_sequences.append(seq)
                dest=self.frequency if kind==0x100 else self.bursts
                dest.extend(accepted)
            return None
        if len(payload)!=4*count:raise ValueError('Truncated command response')
        return kind,seq,words(payload)
    def request(self,kind,payload,count=None):
        self.command_sequence=(self.command_sequence+1)&0xffffffff
        seq=self.command_sequence
        packet=struct.pack('<4I',MAGIC,kind,seq,len(payload) if count is None else count)+struct.pack('<'+'I'*len(payload),*payload)
        for attempt in range(4):
            try:self.sock.send(packet)
            except OSError as error:
                self.reopen_after_link_error(error);self.sock.send(packet)
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                try:reply=self.receive()
                except socket.timeout:continue
                if reply and reply[1]==seq:
                    if reply[0]==0xffffffff:raise RuntimeError(f'Board rejected command {kind}: error {reply[2][0]}')
                    if reply[0]!=(kind|0x80000000):raise ValueError('Wrong command response type')
                    return reply[2]
        raise TimeoutError('No command reply from board; check firmware, board IP, cable and local network configuration')
    def read(self,offset,count=1):return self.request(1,[offset],count)
    def control(self,value):return self.request(2,[value])
    def snapshot(self):
        if not self.read(0x7c)[0]&1:return None
        window_id=self.read(0x80)[0];data=[]
        for offset in range(0,8192,1024):data.extend(self.read(0x3a000+offset,256))
        self.request(5,[2])
        return dict(window_id=window_id,power=[data[i]|data[i+1]<<32 for i in range(0,2048,2)])
    def close(self):self.sock.close()

def export(out,frequency,bursts,metadata):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    # Stream conversion so a 60-second capture does not require hundreds of
    # thousands of decoded dictionaries and one giant JSON string in memory.
    fr=[];ids=set();duplicates=0;max_latency=None
    for kind,raw in [('frequency',frequency),('burst',bursts)]:
        with (out/f'{kind}.bin').open('wb') as f:f.writelines(raw)
        with (out/f'{kind}.json').open('w',encoding='utf-8') as js, (out/f'{kind}.csv').open('w',encoding='utf-8-sig',newline='') as cf:
            js.write('[\n');writer=None
            for n,record in enumerate(raw):
                r=decode_record(record,kind)
                if writer is None:
                    writer=csv.DictWriter(cf,fieldnames=r.keys());writer.writeheader()
                writer.writerow({k:'|'.join(v) if isinstance(v,list) else v for k,v in r.items()})
                if n:js.write(',\n')
                js.write('  '+json.dumps(r,ensure_ascii=False))
                if kind=='frequency':
                    key=(r['epoch'],r['id']);duplicates+=key in ids;ids.add(key)
                    max_latency=r['latency_us'] if max_latency is None else max(max_latency,r['latency_us'])
                    if len(fr)<64:fr.append(r)
            js.write('\n]\n')
    metadata.update(frequency_records=len(frequency),burst_records=len(bursts),
      duplicate_frequency_records=duplicates,maximum_received_latency_us=max_latency)
    (out/'capture.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text=['# IQ 分析记录','',f"- 数据来源：{metadata.get('source','未知')}",
          f'- 频域结果：{len(frequency)} 条',f"- 突发结果：{len(bursts)} 条",
          f"- 接收记录中的最大分析延迟：{metadata['maximum_received_latency_us']} µs",'',
          '> 峰值频率是频谱最高点；调制信号应结合带宽中心观察。单音的 99% 带宽可能为 0，此时分辨率限制标志有效。','',
          '| 窗口 | 峰频率 MHz | 带宽中心 MHz | 99%带宽 MHz | RMS 码值 | 标志 |','|---|---:|---:|---:|---:|---|']
    for r in fr[:64]:text.append(f"| {r['id']} | {r['peak_hz']/1e6:.6f} | {r['bandcenter_hz']/1e6:.6f} | {r['bandwidth_hz']/1e6:.6f} | {r['rms_codes']:.4f} | {', '.join(r['flags'])} |")
    (out/'结果说明.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=False,indent=2))

def capture(args):
    data=Path(args.vector).read_bytes();n=len(data)//4
    if len(data)%4 or n not in (8192,16384,24576,32768):raise ValueError('Replay must contain 8192/16384/24576/32768 signed I16,Q16 pairs')
    client=Client(args.board,args.port);meta={'source':'Zybo UDP board capture','board':args.board,
      'vector':str(Path(args.vector).resolve()),'vector_sha256':hashlib.sha256(data).hexdigest(),'cyclic':args.cyclic}
    callback=getattr(args,'on_update',None);stop_event=getattr(args,'stop_event',None)
    snapshot=None
    started=False
    try:
        if client.read(0)[0]!=0x49514131:raise ValueError('Wrong FPGA design')
        if client.read(8)[0]&7:raise RuntimeError('Board is already running; use the stop command before loading a new capture')
        # Establish a peer, drain any completed records, then discard that earlier epoch locally.
        for _ in range(4):client.read(0x50)
        client.frequency.clear();client.bursts.clear();client.packet_sequences.clear();client._seen_packets.clear()
        # The RAM-load/read-back phase may still drain earlier queued records.
        # Reject that epoch before recording any packet-loss statistics.
        client.active_epoch=(client.read(0x68)[0]+1)&0xffffffff
        for offset in range(0,len(data),1024):
            chunk=words(data[offset:offset+1024]);client.request(3,[offset,*chunk],len(chunk))
        for offset in range(0,len(data),1024):
            expected=data[offset:offset+1024]
            actual=client.read(0x10000+offset,len(expected)//4)
            if struct.pack('<'+'I'*len(actual),*actual)!=expected:raise ValueError(f'Replay read-back mismatch at {offset}')
        meta['replay_readback_verified']=True
        config=[n,int(args.cyclic),int(args.window=='hann'),0,8191,1048576,0,262144,0,8,32,1048576,0]
        client.request(4,config);client.control(1);started=True
        actual_epoch=client.read(0x68)[0]
        if actual_epoch!=client.active_epoch:raise RuntimeError('Acquisition epoch changed unexpectedly')
        meta['epoch']=client.active_epoch
        client.frequency[:]=[r for r in client.frequency if words(r)[2]==client.active_epoch]
        client.bursts[:]=[r for r in client.bursts if words(r)[2]==client.active_epoch]
        begin=time.monotonic();next_status=begin+.05;next_snapshot=begin;stopped=False;drain_until=None
        while True:
            try:client.receive()
            except socket.timeout:pass
            now=time.monotonic()
            if args.cyclic and not stopped and (now-begin>=args.seconds or (stop_event and stop_event.is_set())):
                client.control(2);stopped=True
            if now>=next_status:
                status=client.read(8)[0];next_status=now+.1
                if now>=next_snapshot:
                    shot=client.snapshot()
                    if shot:snapshot=shot
                    if status&7==3 and not client.read(0x7c)[0]:client.request(5,[1])
                    next_snapshot=now+.5
                if callback and client.frequency:
                    callback(dict(record=decode_record(client.frequency[-1],'frequency'),snapshot=snapshot,
                      latest_burst=decode_record(client.bursts[-1],'burst') if client.bursts else None,
                      frequency_records=len(client.frequency),burst_records=len(client.bursts),elapsed_s=now-begin))
                if status&7==0:
                    if drain_until is None:drain_until=now+.5
                    elif now>=drain_until:break
            if now-begin>args.seconds+10:raise TimeoutError('Capture did not stop')
        started=False
        client.request(5,[0]);meta['error_status']=client.read(0x60)[0]
        counters=client.read(0x110,9)
        meta.update(source_ticks=counters[0]|counters[1]<<32,input_samples=counters[2]|counters[3]<<32,
          completed_windows=counters[4],hardware_max_latency_cycles=counters[5],hardware_max_publish_latency_cycles=counters[6],
          frequency_queue_dropped=counters[7],burst_queue_dropped=counters[8])
        seq=client.packet_sequences
        # Signed modular distance handles both reordering and 32-bit wrap.
        meta['udp_missing_packet_count']=packet_loss_count(seq)
        meta['frequency_records_missing']=meta['completed_windows']-len(client.frequency)
        meta['burst_records_missing']=client.read(0x58)[0]-len(client.bursts)
        ids=[words(r)[3] for r in client.frequency]
        meta['frequency_sequence_valid']=sorted(ids)==list(range(meta['completed_windows']))
        meta['sample_count_valid']=meta['completed_windows']>0 and meta['input_samples']==8192*meta['completed_windows']
        meta['analysis_deadline_met']=all(0<meta[k]<=200000 for k in ('hardware_max_latency_cycles','hardware_max_publish_latency_cycles'))
        meta['capture_complete']=not any(meta[k] for k in ('error_status','frequency_records_missing','burst_records_missing',
            'udp_missing_packet_count','frequency_queue_dropped','burst_queue_dropped')) and meta['frequency_sequence_valid'] and meta['sample_count_valid'] and meta['analysis_deadline_met']
    except Exception as error:
        meta.update(capture_complete=False,failure_reason=str(error))
        raise
    finally:
        if started:
            try:client.control(2)
            except (OSError,TimeoutError,RuntimeError):pass
        meta['socket_reopens']=client.socket_reopens
        client.close()
        export(args.out,client.frequency,client.bursts,meta)
        if snapshot:
            out=Path(args.out)
            (out/'snapshot.json').write_text(json.dumps(snapshot,indent=2)+'\n',encoding='utf-8')
            (out/'snapshot.bin').write_bytes(struct.pack('<1024Q',*snapshot['power']))
    if callback and client.frequency:
        callback(dict(record=decode_record(client.frequency[-1],'frequency'),snapshot=snapshot,
            latest_burst=decode_record(client.bursts[-1],'burst') if client.bursts else None,
            frequency_records=len(client.frequency),burst_records=len(client.bursts),metadata=meta))
    if not meta.get('capture_complete'):raise RuntimeError('Capture has missing records or hardware errors; inspect capture.json')

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('capture');c.add_argument('--board',default='192.168.1.10');c.add_argument('--port',type=int,default=5001)
    c.add_argument('--vector',required=True);c.add_argument('--out',required=True);c.add_argument('--window',choices=['rect','hann'],default='hann')
    c.add_argument('--cyclic',action='store_true');c.add_argument('--seconds',type=float,default=1)
    d=sub.add_parser('decode');d.add_argument('--freq',required=True);d.add_argument('--burst');d.add_argument('--out',required=True)
    s=sub.add_parser('stop');s.add_argument('--board',default='192.168.1.10');s.add_argument('--abort',action='store_true')
    a=p.parse_args()
    if a.command=='capture':capture(a)
    elif a.command=='stop':
        c=Client(a.board)
        try:c.control(4 if a.abort else 2)
        finally:c.close()
    else:
        f=Path(a.freq).read_bytes();b=Path(a.burst).read_bytes() if a.burst else b''
        if len(f)%128 or len(b)%64:raise ValueError('Truncated binary record file')
        export(a.out,[f[i:i+128] for i in range(0,len(f),128)],[b[i:i+64] for i in range(0,len(b),64)],{'source':'Imported binary records; see original capture provenance'})
if __name__=='__main__':main()
