"""Duration-based Phase 8 DDR/DMA board test with continuous PC uploads."""
from __future__ import annotations
import argparse,datetime,json,socket,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'scripts')]
from iq_client import Client,DMA_VERSION,decode_record,packet_loss_count
from phase4_identity import check_identity
from record_build_stage import sha
from streaming import SIGNALS,make_signal

def now():return datetime.datetime.now().astimezone().isoformat()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def drain(client,stats,seconds=.01):
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
    p.add_argument('--board',default='192.168.1.10');p.add_argument('--seconds',type=float,required=True)
    p.add_argument('--samples',type=int,choices=(8192,16384,24576,32768),default=8192)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.seconds<1:raise ValueError('--seconds must be at least 1')
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(status='RUNNING',started_at=now(),board=a.board,duration_requested_s=a.seconds,
        samples_per_bank=a.samples,scope='PC continuously fills DDR and DMA loads the inactive bank while FPGA analyzes at 125 MSPS',
        artifacts={n:sha(ROOT/'artifacts'/n) for n in ('iq_analyzer.bit','iq_udp.elf')})
    save(out/'stability.json',report);client=Client(a.board);started=False
    stats=dict(frequency_records=0,burst_records=0,maximum_latency_us=0.0,last_frequency_id=None,frequency_id_gaps=0)
    try:
        info=client.hardware_info();check_identity(info)
        if info['hardware_version']<DMA_VERSION or info['hardware_capabilities']&12!=12:raise AssertionError('DDR/DMA capability absent')
        report['hardware']=info
        client.configure([a.samples,1,1,0,8191,1048576,0,262144,0,8,32,1048576,0],hardware=info)
        cached={kind:make_signal(kind,a.samples,index+1) for index,kind in enumerate(SIGNALS)}
        dma_base=client.stream_status()['dma']['completed_transfers']
        client.upload_stream_block(cached['single'],0,1,arm=True)
        client.control(1);started=True;client.active_epoch=client.read(0x68)[0]
        initial=wait_block(client,1,stats);base_switches=initial['switch_count']
        begin=time.monotonic();deadline=begin+a.seconds;block_id=1;uploads=[]
        while time.monotonic()<deadline:
            block_id+=1;kind=SIGNALS[(block_id-1)%len(SIGNALS)]
            status=client.stream_status();bank=1-status['active_bank'];upload_begin=time.monotonic()
            crc,_=client.upload_stream_block(cached[kind],bank,block_id,arm=True)
            status=wait_block(client,block_id,stats);uploads.append(time.monotonic()-upload_begin)
            if status['active_bank']!=bank or status['block_ids'][bank]!=block_id or status['crc32'][bank]!=crc:
                raise AssertionError(f'bank metadata mismatch at block {block_id}')
            if status['dma']['active'] or not status['dma']['done'] or status['dma']['error'] or status['dma']['errors']:
                raise AssertionError(f'DMA telemetry failed at block {block_id}: {status["dma"]}')
        elapsed=time.monotonic()-begin;final=client.stream_status();client.control(2)
        stop_deadline=time.monotonic()+10
        while client.read(8)[0]&7:
            drain(client,stats,.02)
            if time.monotonic()>stop_deadline:raise TimeoutError('STOP did not drain')
        started=False;drain(client,stats,.5);client.request(5,[0])
        diag=client.diagnostics();counters=client.read(0x110,9);error_status=client.read(0x60)[0]
        stats['udp_missing_packet_count']=packet_loss_count(client.packet_sequences)
        stats['recovered_malformed_packets']=client.malformed_packets
        expected_switches=block_id-1
        if final['switch_count']-base_switches!=expected_switches:raise AssertionError('switch counter mismatch')
        if final['dma']['completed_transfers']-dma_base!=expected_switches+1:raise AssertionError('DMA transfer counter mismatch')
        if final['write_rejected'] or final['stream_errors']:raise AssertionError(f'stream RTL errors: {final}')
        if error_status or counters[7] or counters[8]:raise AssertionError(f'hardware/result drop: {error_status:#x}, {counters[7:9]}')
        if not(diag['issued_samples']==diag['accepted_samples']==diag['fft_input_samples']==diag['fft_output_samples']):
            raise AssertionError(f'sample conservation failed: {diag}')
        if diag['input_rejected'] or diag['result_queue_rejected'] or diag['input_underreads']:
            raise AssertionError(f'diagnostic error: {diag}')
        if stats['frequency_id_gaps'] or stats['udp_missing_packet_count'] or stats['frequency_records']!=counters[4]:
            raise AssertionError(f'record integrity failed: completed={counters[4]} stats={stats}')
        report.update(status='PASS',finished_at=now(),duration_actual_s=elapsed,switches=expected_switches,
            final_status=final,statistics=stats,diagnostics=diag,completed_windows=counters[4],
            hardware_max_latency_us=counters[5]*1e6/info['timestamp_clock_hz'],
            hardware_max_publish_latency_us=counters[6]*1e6/info['timestamp_clock_hz'],
            average_upload_seconds=sum(uploads)/len(uploads),maximum_upload_seconds=max(uploads),
            effective_average_upload_mbps=a.samples*32/1e6/(sum(uploads)/len(uploads)))
        if report['hardware_max_latency_us']>2000 or report['hardware_max_publish_latency_us']>2000:
            raise AssertionError('2 ms deadline failed')
    except Exception as error:
        report.update(status='FAIL',finished_at=now(),error=str(error));raise
    finally:
        if started:
            try:client.control(2)
            except Exception:pass
        client.close();save(out/'stability.json',report)
    print('PHASE8_DDR_DMA_STABILITY_PASS',a.seconds,out)

if __name__=='__main__':main()
