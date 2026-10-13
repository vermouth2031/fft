"""Run only after this turn's explicit user confirmation of a physical cycle."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'host'),str(root/'scripts')]
from iq_client import Client
from phase4_identity import check_identity

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--user-confirmation',required=True)
args=parser.parse_args()
assert args.user_confirmation.strip()
out=root/'reports/phase13_cold_boot_20261013'
assert not out.exists(),'Preserve existing physical-cycle attempt'
out.mkdir()
os.environ['PYTHONUTF8']='1'
os.environ['IQ_CLIENT_SOURCE_IP']='192.168.1.20'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
client=Client('192.168.1.10',source_ip='192.168.1.20')
try:
    hardware=client.hardware_info();check_identity(hardware)
    before=dict(hardware=hardware,state=client.read(8)[0],errors=client.read(0x60)[0],epoch=client.read(0x68)[0])
finally:
    client.close()
initial=dict(checked_at=datetime.datetime.now().astimezone().isoformat(),user_confirmation=args.user_confirmation,
    jtag_used=False,program_download_performed=False,system_reset_performed=False,before=before,
    sd_deployment_sha256=sha(root/'reports/phase13_sd_deployment.json'),
    boot_sha256=sha(root/'artifacts/BOOT_udp.BIN'))
(out/'initial_state.json').write_text(json.dumps(initial,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert before['epoch']==0 and before['state']&7==0 and before['errors']==0,before
print('PHASE13_PHYSICAL_CYCLE_NETWORK_IDENTITY_PASS',flush=True)
def run(arguments,name):
    with (root/'build/logs'/name).open('w',encoding='utf-8') as log:
        subprocess.run([sys.executable,*arguments],cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
    print('STAGE_PASS',arguments[0],flush=True)
run(['scripts/phase13_board_validation.py','--references','build/phase13_finite/reference_trial09/index.json',
     '--out',str(out/'finite')],'phase13_cold_finite.txt')
run(['scripts/phase13_wideband_stability.py','--seconds','300','--samples','32768','--out',str(out/'continuous300')],
    'phase13_cold_continuous300.txt')
run(['.local/phase13_probe.py',str(out/'final_state.json')],'phase13_cold_final.txt')
(out/'execution_script.py').write_bytes(Path(__file__).read_bytes())
run(['scripts/record_phase13_deployment.py','cold','--finite',str(out/'finite/validation.json'),
     '--final-state',str(out/'final_state.json'),'--initial-state',str(out/'initial_state.json'),
     '--continuous300',str(out/'continuous300/stability.json')],'phase13_cold_record.txt')
print('PHASE13_PHYSICAL_COLD_BOOT_COMPLETE',flush=True)
