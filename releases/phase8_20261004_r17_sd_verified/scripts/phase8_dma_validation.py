"""Repeatable Phase 8 DDR/DMA real-board acceptance and throughput test."""
from __future__ import annotations
import argparse,datetime,json,socket,struct,sys,time,zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'scripts')]
from iq_client import Client,DMA_VERSION,decode_record,packet_loss_count
from phase4_identity import check_identity
from record_build_stage import sha
from streaming import SIGNALS,make_signal

def now():return datetime.datetime.now().astimezone().isoformat()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def rejected(client,kind,payload,error):
    try:client.request(kind,payload)
    except RuntimeError as exc:
        if f'error {error}' not in str(exc):raise
        return
    raise AssertionError(f'Command {kind} was not rejected with error {error}')

def drain(client,stats,seconds=.02):
    deadline=time.monotonic()+seconds;client.sock.settimeout(.001)
    try:
        while time.monotonic()<deadline:
            try:client.receive()
            except socket.timeout:continue
    finally:client.sock.settimeout(.5)
    for raw in client.frequency:
        row=decode_record(raw,'frequency');stats['frequency_records']+=1
        stats['maximum_latency_us']=max(stats['maximum_latency_us'],row['latency_us'])
        if stats['last_frequency_id'] is not None and row['id']!=stats['last_frequency_id']+1:
            stats['frequency_id_gaps']+=1
            if len(stats['frequency_gap_examples'])<16:
                stats['frequency_gap_examples'].append([stats['last_frequency_id'],row['id']])
        stats['last_frequency_id']=row['id']
    stats['burst_records']+=len(client.bursts)
    client.frequency.clear();client.bursts.clear()

def wait_block(client,block_id,stats,timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        status=client.stream_status()
        if status['current_block_id']==block_id and not status['pending_valid']:
            drain(client,stats);return status
    raise TimeoutError(f'block {block_id} did not become active')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board',default='192.168.1.10');p.add_argument('--source-ip',help='Local IPv4 address for the board NIC; overrides IQ_CLIENT_SOURCE_IP');p.add_argument('--switches',type=int,default=1000)
    p.add_argument('--samples',type=int,choices=(8192,16384,24576,32768),default=8192)
    p.add_argument('--minimum-upload-mbps',type=float,default=8.0)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.switches<12:raise ValueError('--switches must be at least 12')
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(status='RUNNING',started_at=now(),board=a.board,switches_requested=a.switches,
        samples_per_bank=a.samples,minimum_upload_mbps=a.minimum_upload_mbps,
        scope='Real board: PC writes DDR, AXI DMA loads inactive PL bank, active bank runs at 125 MSPS',
        faults=[],signals=list(SIGNALS),artifacts={n:sha(ROOT/'artifacts'/n) for n in ('iq_analyzer.bit','iq_udp.elf')})
    save(out/'validation.json',report);client=Client(a.board,source_ip=a.source_ip);started=False
    stats=dict(frequency_records=0,burst_records=0,maximum_latency_us=0.0,last_frequency_id=None,
        frequency_id_gaps=0,frequency_gap_examples=[])
    try:
        info=client.hardware_info();check_identity(info)
        if info['hardware_version']<DMA_VERSION or info['hardware_capabilities']&12!=12:raise AssertionError('DDR/DMA capability absent')
        report['hardware']=info
        config=[a.samples,1,1,0,8191,1048576,0,262144,0,8,32,1048576,0]
        client.configure(config,hardware=info)

        word=struct.pack('<I',0x12345678);good=zlib.crc32(word)&0xffffffff
        rejected(client,6,[0,0x1000,0,good^1,0x12345678],6)
        report['faults'].append({'name':'packet_crc_corruption','status':'REJECTED'})
        client.request(6,[0,0x1001,0,good,0x12345678])
        rejected(client,6,[0,0x1001,2,good,0x12345678],5);client.abort_stream_upload(0)
        report['faults'].append({'name':'out_of_order_offset','status':'REJECTED'})
        client.request(6,[0,0x1002,0,good,0x12345678])
        rejected(client,7,[0,0x1002,a.samples,zlib.crc32(word)&0xffffffff,0],6);client.abort_stream_upload(0)
        report['faults'].append({'name':'incomplete_commit','status':'REJECTED'})

        cached={kind:make_signal(kind,a.samples,index+1) for index,kind in enumerate(SIGNALS)}
        dma_base=client.stream_status()['dma']['completed_transfers']
        _,initial=client.upload_stream_block(cached['single'],0,1,arm=True)
        client.control(1);started=True;client.active_epoch=client.read(0x68)[0]
        initial=wait_block(client,1,stats);base_switches=initial['switch_count']
        active_word=struct.unpack('<I',cached['single'][:4])[0]
        rejected(client,6,[initial['active_bank'],0x2000,0,zlib.crc32(cached['single'][:4])&0xffffffff,active_word],3)
        report['faults'].append({'name':'active_bank_write','status':'REJECTED_BY_FIRMWARE'})

        uploads=[]
        for transition in range(1,a.switches+1):
            block_id=transition+1;kind=SIGNALS[transition%len(SIGNALS)]
            status=client.stream_status();bank=1-status['active_bank'];begin=time.monotonic()
            crc,status=client.upload_stream_block(cached[kind],bank,block_id,arm=True)
            status=wait_block(client,block_id,stats);elapsed=time.monotonic()-begin
            if status['active_bank']!=bank or status['block_ids'][bank]!=block_id or status['crc32'][bank]!=crc:
                raise AssertionError(f'bank metadata mismatch at transition {transition}')
            if status['dma']['active'] or not status['dma']['done'] or status['dma']['error'] or status['dma']['errors']:
                raise AssertionError(f'DMA telemetry failed at transition {transition}: {status["dma"]}')
            if status['dma']['received_samples']!=a.samples or status['dma']['computed_crc32']!=crc:
                raise AssertionError(f'DMA length/CRC mismatch at transition {transition}: {status["dma"]}')
            uploads.append(elapsed)
            if transition%25==0:
                save(out/'progress.json',dict(transition=transition,status=status,stats=stats,
                    average_upload_seconds=sum(uploads)/len(uploads)))
                print('PHASE8_SWITCH_PASS',transition,flush=True)

        final=client.stream_status()
        if final['switch_count']-base_switches!=a.switches:raise AssertionError('switch counter mismatch')
        if final['dma']['completed_transfers']-dma_base!=a.switches+1:raise AssertionError('DMA transfer counter mismatch')
        if final['write_rejected'] or final['stream_errors']:raise AssertionError(f'stream RTL errors: {final}')
        client.control(2)
        deadline=time.monotonic()+10
        while client.read(8)[0]&7:
            drain(client,stats,.02)
            if time.monotonic()>deadline:raise TimeoutError('STOP did not drain')
        started=False;drain(client,stats,.5)
        client.request(5,[0]);diag=client.diagnostics();counters=client.read(0x110,9)
        error_status=client.read(0x60)[0]
        stats['udp_missing_packet_count']=packet_loss_count(client.packet_sequences)
        stats['recovered_malformed_packets']=client.malformed_packets
        if error_status or counters[7] or counters[8]:raise AssertionError(f'hardware/result drop: {error_status:#x}, {counters[7:9]}')
        if not(diag['issued_samples']==diag['accepted_samples']==diag['fft_input_samples']==diag['fft_output_samples']):
            raise AssertionError(f'sample conservation failed: {diag}')
        if diag['input_rejected'] or diag['result_queue_rejected'] or diag['input_underreads']:
            raise AssertionError(f'diagnostic error: {diag}')
        if stats['frequency_id_gaps'] or stats['udp_missing_packet_count'] or stats['frequency_records']!=counters[4] or stats['maximum_latency_us']>2000:
            raise AssertionError(f'record integrity failed: completed={counters[4]} stats={stats}')
        average_upload=sum(uploads)/len(uploads);effective_mbps=a.samples*32/1e6/average_upload
        report.update(average_upload_seconds=average_upload,maximum_upload_seconds=max(uploads),
            effective_average_upload_mbps=effective_mbps,completed_transitions=len(uploads))
        if effective_mbps<a.minimum_upload_mbps:raise AssertionError(f'upload throughput {effective_mbps:.3f} Mbit/s below {a.minimum_upload_mbps:.3f}')
        report.update(status='PASS',finished_at=now(),final_status=final,statistics=stats,diagnostics=diag,
            source_ticks=counters[0]|counters[1]<<32,input_samples=counters[2]|counters[3]<<32,
            completed_windows=counters[4],hardware_max_latency_us=counters[5]*1e6/info['timestamp_clock_hz'],
            hardware_max_publish_latency_us=counters[6]*1e6/info['timestamp_clock_hz'],
            average_upload_seconds=average_upload,maximum_upload_seconds=max(uploads),
            effective_average_upload_mbps=effective_mbps,
            throughput_semantics='PC UDP payload into DDR plus commit DMA and activation wait; FPGA consumes active bank independently at 125 MSPS')
        if report['hardware_max_latency_us']>2000 or report['hardware_max_publish_latency_us']>2000:
            raise AssertionError('2 ms deadline failed')
    except Exception as error:
        report.update(status='FAIL',finished_at=now(),error=str(error));raise
    finally:
        if started:
            try:client.control(2)
            except Exception:pass
        client.close();save(out/'validation.json',report)
    print('PHASE8_DDR_DMA_BOARD_PASS',out)

if __name__=='__main__':main()
