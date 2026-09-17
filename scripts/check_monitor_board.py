"""Exercise the real Tk callbacks against the attached board and save visual evidence."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
import tkinter as tk
from PIL import ImageGrab
from monitor import Monitor,enable_dpi_awareness
out=ROOT/'captures/extended_20260917/gui';out.mkdir(exist_ok=True)
enable_dpi_awareness();root=tk.Tk();app=Monitor(root);phase=0;deadline=time.monotonic()+90;results=[]
def save_screen(name):
    root.update_idletasks()
    ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(out/name)
def step():
    global phase
    try:
        if time.monotonic()>deadline:raise TimeoutError('GUI test timed out')
        if phase==0:
            app.seconds.set('3');app.start_button.invoke();phase=1
        elif phase in (1,2) and app.worker and not app.worker.is_alive() and not app.start_button.instate(['disabled']):
            status=app.status.get();assert '采集完整性检查通过' in status,status
            directory=Path(status.split('：',1)[1]);meta=json.loads((directory/'capture.json').read_text())
            assert meta['capture_complete'] and '最近突发长度' in app.metrics.get()
            assert len(app.env.find_all())>5 and len(app.spec.find_all())>5
            results.append({'phase':'timed_capture' if phase==1 else 'window_boundary_stop','capture':str(directory),'metadata':meta,'metrics':app.metrics.get()})
            save_screen('live_capture.png' if phase==1 else 'stopped_capture.png')
            if phase==1:
                app.seconds.set('10');app.start_button.invoke();root.after(2500,app.stop_event.set);phase=2
            else:
                assert meta['input_samples']<5e8
                app.load_capture(ROOT/'captures/network_20260917_211639/qpsk_10s');phase=3
        elif phase==3:
            assert '离线查看' in app.status.get() and '最近突发长度' in app.metrics.get()
            save_screen('offline_capture.png')
            (out/'gui_validation.json').write_text(json.dumps({'status':'PASS','tests':results,'offline_load':True},ensure_ascii=False,indent=2),encoding='utf-8')
            root.destroy();return
    except Exception as e:
        (out/'gui_error.txt').write_text(repr(e),encoding='utf-8');app.stop_event.set();root.destroy();raise
    root.after(150,step)
root.after(300,step);root.mainloop()
assert (out/'gui_validation.json').exists(),'GUI validation did not finish'
print('GUI_BOARD_PASS')
