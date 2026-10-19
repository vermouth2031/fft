import sys,time,json,hashlib
from pathlib import Path
from PIL import ImageGrab
W=Path(r'D:/fft/report8_edit_20261014');P=Path(r'D:/fft/fft_phase13_reproduction_20261013')
sys.path.insert(0,str(P/'host'));import monitor;import tkinter as tk
monitor.enable_dpi_awareness();root=tk.Tk();app=monitor.Monitor(root);root.geometry('1500x1100+30+30');root.attributes('-topmost',True)
def pump():
 for _ in range(25):root.update();time.sleep(.025)
manifest=[]
for name,fig in [('ofdm_qpsk_212100_hann','figure4_7'),('noise_10_91001_hann','figure4_9')]:
 folder=Path(r'D:/fft/report4_capture_20261014/finite')/name;app.load_capture(folder);pump()
 u=dict(app._last_update);shot=u['snapshot'];raw=(folder/'frequency.bin').read_bytes();records=[monitor.decode_record(raw[i:i+128],'frequency') for i in range(0,len(raw),128)];r=next(r for r in records if r['id']==shot['window_id']);u['record']=r;app.show_update(u);pump()
 assert app._last_update['record']['id']==app._last_update['snapshot']['window_id']==0
 ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(W/(fig+'.png'))
 manifest.append(dict(figure=fig,folder=str(folder),record=r,snapshot_window=shot['window_id'],metrics=app.metrics.get(),frequency_sha256=hashlib.sha256(raw).hexdigest(),snapshot_sha256=hashlib.sha256((folder/'snapshot.json').read_bytes()).hexdigest()))
root.destroy();(W/'screenshot_evidence.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print('Captured matching window 0 for both figures')