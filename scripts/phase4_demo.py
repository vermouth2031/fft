"""Four reviewable presets around the unchanged production GUI/CLI capture path."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'scripts')]
import monitor

def presets():
    rows=json.loads((ROOT/'data/phase4_demo/presets.json').read_text(encoding='utf-8'))['presets']
    for row in rows:
        path=ROOT/row['vector']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Demo vector changed: '+row['id'])
        if row.get('reference_sha256') and hashlib.sha256((ROOT/row['reference']).read_bytes()).hexdigest()!=row['reference_sha256']:
            raise ValueError('Demo reference changed: '+row['id'])
    return rows

class DemoMonitor(monitor.Monitor):
    def __init__(self,root):
        super().__init__(root);self.presets=presets()
        menu=monitor.tk.Menu(root);choices=monitor.tk.Menu(menu,tearoff=False)
        for row in self.presets:choices.add_command(label=row['label'],command=lambda p=row:self.apply_preset(p))
        menu.add_cascade(label='演示预设',menu=choices);root.config(menu=menu)
        self.apply_preset(self.presets[-1])
    def apply_preset(self,row):
        if self.worker and self.worker.is_alive():return
        self.vector.set(str(ROOT/row['vector']));self.window.set(row['window'])
        self.detector.set(row['detector']);self.gap_min.set('32');self.cyclic.set(row['cyclic'])
        self.seconds.set(str(row['seconds']));self.threshold_profile.set(row['profile'])
        self.threshold_policy.set('quiet-prefix' if row['profile']=='robust' else 'fixed')
        self.quiet_samples.set('1024')
        for value in self.threshold_values.values():value.set('')
        self.status.set(row['label']+'。'+row['meaning']);self.envelope()
    def show_update(self,u):
        super().show_update(u);r=u['record']
        text=self.metrics.get().replace('  中心 ','  带宽中心 ').replace('  |  延迟 ','  |  PL 分析延迟 ')
        if '板内回放 I16/Q16' not in text:
            text=f"板内回放 I16/Q16，各 16bit  |  {r['sample_rate_hz']/1e6:g} M 对 IQ/秒  |  FFT {r['fft_length']}  |  窗 {r['window']}\n"+text
        self.metrics.set(text)

def main():
    p=argparse.ArgumentParser();p.add_argument('--preset',choices=('digital','robust','tone','ofdm'),default='ofdm')
    p.add_argument('--list',action='store_true');a=p.parse_args()
    rows=presets()
    if a.list:
        print(json.dumps(rows,ensure_ascii=False,indent=2));return
    monitor.enable_dpi_awareness();root=monitor.tk.Tk();app=DemoMonitor(root)
    app.apply_preset(next(r for r in rows if r['id']==a.preset));root.mainloop()
if __name__=='__main__':main()
