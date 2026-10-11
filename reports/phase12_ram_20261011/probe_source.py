import datetime,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'scripts')]
from iq_client import Client
from phase4_identity import check_identity
out=Path(sys.argv[1]);deadline=time.monotonic()+45
while True:
    client=Client('192.168.1.10',source_ip='192.168.1.20')
    try:
        hardware=client.hardware_info();check_identity(hardware)
        report=dict(checked_at=datetime.datetime.now().astimezone().isoformat(),
                    hardware=hardware,state=client.read(8)[0],errors=client.read(0x60)[0],epoch=client.read(0x68)[0])
        assert report['state']&7==0 and report['errors']==0,report
        out.write_text(json.dumps(report,indent=2)+'\n')
        print('PHASE12_IDLE_NETWORK_IDENTITY_PASS',json.dumps(report));break
    except Exception:
        if time.monotonic()>=deadline:raise
        time.sleep(1)
    finally:client.close()
