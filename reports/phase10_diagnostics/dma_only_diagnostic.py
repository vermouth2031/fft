import sys,json,time,traceback,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'host'),str(root/'scripts')]
from iq_client import Client
from streaming import make_signal,SIGNALS
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
report={'status':'RUNNING','diagnostic_only':True,'clock_note':sys.argv[2],
 'started_at':time.time(),'completed':0,
 'artifacts':{n:hashlib.sha256((root/'artifacts'/n).read_bytes()).hexdigest() for n in ('iq_analyzer.bit','iq_udp.elf')}}
client=Client('192.168.1.10',source_ip='192.168.1.20')
try:
 info=client.hardware_info();report['hardware']=info
 assert info['build_id']=='fee5b8547053d9807159a1aa1bd5482c'
 client.configure([16384,1,1,0,16383,1048576,0,262144,0,8,32,1048576,0],hardware=info)
 data={k:make_signal(k,16384,i+1) for i,k in enumerate(SIGNALS)}
 for i in range(1000):
  crc,s=client.upload_stream_block(data[SIGNALS[i%len(SIGNALS)]],i%2,i+1,arm=False,pipeline=int(sys.argv[3]) if len(sys.argv)>3 else 4)
  assert s['dma']['done'] and not s['dma']['error'] and s['dma']['computed_crc32']==crc
  report['completed']=i+1
  if i%25==24:print('DMA_ONLY_PASS',i+1,flush=True)
 report['status']='PASS'
except Exception as e:
 report['status']='FAIL';report['error']=str(e)
 traceback.print_exc()
finally:
 try:report['final_status']=client.stream_status()
 except Exception as e:report['status_read_error']=str(e)
 client.close();report['finished_at']=time.time()
 (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
