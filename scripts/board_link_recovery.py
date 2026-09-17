"""Capture across a controlled wired-adapter outage, retaining the same UDP socket."""
import json,sys,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
import iq_client as h
OUT=ROOT/'captures/extended_20260917/link_interrupt_fixed'
original=h.Client
# Use the production Client's Windows socket recovery in the fixed-version test.
def update(_):
    if not (OUT/'trigger.txt').exists():(OUT/'trigger.txt').write_text('Interrupt this capture')
error=None
try:
    h.capture(SimpleNamespace(board='192.168.1.10',port=5001,vector=str(ROOT/'data/vectors/qpsk_sps4.bin'),out=str(OUT/'interrupted'),window='hann',cyclic=True,seconds=12,on_update=update))
except Exception as exc:error=str(exc)
finally:h.Client=original
meta=json.loads((OUT/'interrupted/capture.json').read_text())
assert error and not meta.get('capture_complete'),(error,meta)
assert (OUT/'adapter_events.json').exists()
# Normal capture cleanup must finish STOP before another UDP peer can take over.
for _ in range(30):
    try:
        c=original('192.168.1.10');state=c.read(8)[0];c.close()
        if state&7==0:break
    except (OSError,TimeoutError):pass
    time.sleep(.2)
else:raise RuntimeError('Board not stopped after link restoration; explicit recovery required')
h.capture(SimpleNamespace(board='192.168.1.10',port=5001,vector=str(ROOT/'data/vectors/tone_pos_fs4.bin'),out=str(OUT/'recovery'),window='hann',cyclic=False,seconds=1))
assert meta.get('socket_reopens',0)>0 and 'error_status' in meta
assert not (OUT/'jtag_recovery.txt').exists()
report={'status':'PASS','method':'Disable only the board-facing Realtek adapter for 3 seconds, then re-enable',
        'interrupted_capture_exception':error,'interrupted_capture':meta,
        'jtag_intervention':False,'recovery':json.loads((OUT/'recovery/capture.json').read_text())}
(OUT/'link_recovery.json').write_text(json.dumps(report,indent=2))
print('LINK_RECOVERY_PASS')
