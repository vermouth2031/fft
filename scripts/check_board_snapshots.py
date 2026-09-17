"""Compare archived PL display snapshots to the existing AMD integer FFT oracle."""
from pathlib import Path
import hashlib,json,struct
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
gold=json.loads((ROOT/'data/golden_results.json').read_text())['cases']
packed=np.array([int(line,16) for line in (ROOT/'data/golden_fft.mem').read_text().splitlines()],dtype=np.int64).reshape(16,4,8192)
re=((packed&0xffffff)^0x800000)-0x800000
im=(((packed>>24)&0xffffff)^0x800000)-0x800000
expected=np.fft.fftshift(re*re+im*im,axes=2).reshape(16,4,1024,8).max(axis=3)
checked=[]
def check(path,case,window,actual):
    assert np.array_equal(np.array(actual,dtype=np.int64),expected[case,window%4]),str(path)
    checked.append({'file':str(path.relative_to(ROOT)),'case':case,'window':window,'bins':1024})
sd=ROOT/'captures/sd_board_20260917_202436/raw'
for run in sorted(sd.glob('RUN*')):
    for case in range(16):
        d=run/f'C{case:02d}';meta=json.loads((d/'META.JSON').read_text());p=d/'SNAP.BIN'
        check(p,case,meta['snapshot_window'],struct.unpack('<1024Q',p.read_bytes()))
for p in sorted((ROOT/'captures').rglob('snapshot.json')):
    meta_path=p.parent/'capture.json'
    if not meta_path.exists():continue
    meta=json.loads(meta_path.read_text());name=Path(meta.get('vector','')).stem
    case=next((i for i,g in enumerate(gold) if g['name']==name and g['mode']=='hann'),None)
    if case is None:continue
    original=ROOT/'data/vectors'/(name+'.bin')
    if meta.get('vector_sha256')!=hashlib.sha256(original.read_bytes()).hexdigest():continue
    shot=json.loads(p.read_text());check(p,case,shot['window_id'],shot['power'])
report={'status':'PASS','reference':'AMD bit-accurate FFT; fftshift and max over each 8 bins',
        'snapshots':len(checked),'exact_power_values':len(checked)*1024,'files':checked}
(ROOT/'reports/board_snapshot_validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('BOARD_SNAPSHOT_PASS',len(checked),len(checked)*1024)
