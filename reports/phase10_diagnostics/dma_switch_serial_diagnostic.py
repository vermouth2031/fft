import sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'host'),str(root/'scripts')]
import phase8_dma_validation as v
original=v.Client.upload_stream_block
def upload(self,*args,**kwargs):
 kwargs['pipeline']=1
 return original(self,*args,**kwargs)
v.Client.upload_stream_block=upload
out=root/'reports/phase10_dma_switch_serial_20261009'
sys.argv=[sys.argv[0],'--switches','1000','--samples','16384','--source-ip','192.168.1.20','--out',str(out)]
try:v.main()
finally:
 p=out/'validation.json'
 if p.exists():
  r=json.loads(p.read_text());r['diagnostic_only']=True;r['host_upload_pipeline']=1
  p.write_text(json.dumps(r,indent=2)+'\n')
