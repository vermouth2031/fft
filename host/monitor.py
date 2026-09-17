"""Tk desktop monitor; uses hardware results and labels replay input explicitly."""
from pathlib import Path
from types import SimpleNamespace
import json, math, queue, struct, threading, time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from iq_client import capture,decode_record
ROOT=Path(__file__).resolve().parents[1]

def enable_dpi_awareness():
    import sys
    if sys.platform=='win32':
        import ctypes
        try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError,OSError):pass

class Monitor:
    def __init__(self,root):
        self.root=root;root.title('Zybo Z7-20 | IQ 频谱分析')
        root.geometry(f'{min(1180,root.winfo_screenwidth()-80)}x{min(920,root.winfo_screenheight()-100)}');root.minsize(900,720)
        self.messages=queue.Queue();self.worker=None;self.stop_event=threading.Event()
        self.board=tk.StringVar(value='192.168.1.10')
        self.vector=tk.StringVar(value=str(ROOT/'data/vectors/qpsk_sps4.bin'))
        self.window=tk.StringVar(value='hann');self.seconds=tk.StringVar(value='10')
        form=ttk.Frame(root,padding=12);form.pack(fill='x')
        for col,(label,var,width) in enumerate([('板卡 IP',self.board,18),('持续秒数',self.seconds,8)]):
            ttk.Label(form,text=label).grid(row=0,column=col*2,padx=4)
            ttk.Entry(form,textvariable=var,width=width).grid(row=0,column=col*2+1)
        ttk.Combobox(form,textvariable=self.window,values=['rect','hann'],state='readonly',width=8).grid(row=0,column=4,padx=8)
        buttons=ttk.Frame(form);buttons.grid(row=1,column=0,columnspan=6,sticky='w',pady=8)
        self.start_button=ttk.Button(buttons,text='开始连续采集',command=self.start);self.start_button.pack(side='left',padx=4)
        ttk.Button(buttons,text='窗口边界停止',command=self.stop_event.set).pack(side='left',padx=4)
        ttk.Button(buttons,text='打开已有记录',command=self.open_capture).pack(side='left',padx=4)
        ttk.Entry(form,textvariable=self.vector,width=65).grid(row=2,column=0,columnspan=5,pady=4,sticky='we')
        ttk.Button(form,text='选择 IQ 文件',command=self.choose_vector).grid(row=2,column=5,padx=8)
        form.columnconfigure(4,weight=1)
        self.status=tk.StringVar(value='等待连接。100 MSPS / 8192 点；展示数值来自 PL。')
        status_label=ttk.Label(root,textvariable=self.status,padding=12,wraplength=1050);status_label.pack(fill='x')
        root.bind('<Configure>',lambda e:status_label.configure(wraplength=max(500,e.width-30)) if e.widget is root else None)
        self.metrics=tk.StringVar(value='幅度、帧数、频率、99% 带宽和处理延迟将在采集后显示。')
        ttk.Label(root,textvariable=self.metrics,padding=12,font=('Microsoft YaHei UI',11)).pack(fill='x')
        self.env=tk.Canvas(root,height=190,bg='#f7f9fc',highlightthickness=0);self.env.pack(fill='both',expand=True,padx=14,pady=6)
        self.spec=tk.Canvas(root,height=280,bg='#f7f9fc',highlightthickness=0);self.spec.pack(fill='both',expand=True,padx=14,pady=6)
        for canvas in (self.env,self.spec):
            canvas.bind('<Configure>',lambda e:self.draw(e.widget,*e.widget._last_plot) if hasattr(e.widget,'_last_plot') else None)
        ttk.Label(root,text='频谱：PL 每 8 个 bin 取最大值的显示快照；99% 带宽由完整 8192 点计算。',padding=12).pack(fill='x')
        root.after(150,self.poll);root.protocol('WM_DELETE_WINDOW',self.close)

    def choose_vector(self):
        p=filedialog.askopenfilename(filetypes=[('IQ binary','*.bin')])
        if p:self.vector.set(p)

    def draw(self,canvas,values,title,unit,xleft,xright,fixed=None):
        canvas._last_plot=(values,title,unit,xleft,xright,fixed)
        canvas.delete('all');w=max(canvas.winfo_width(),700);h=max(canvas.winfo_height(),180)
        canvas.create_text(16,14,anchor='nw',text=title,fill='#193353',font=('Microsoft YaHei UI',10))
        left,top,right,bottom=90,45,w-24,h-35
        low,high=fixed or (min(values,default=0),max(values,default=1))
        if high==low:low=0;high=max(1,high)
        for j in range(5):
            y=top+(bottom-top)*j/4;value=high-(high-low)*j/4
            canvas.create_line(left,y,right,y,fill='#dce3ec')
            canvas.create_text(left-8,y,text=f'{value:.1f}',anchor='e',fill='#51647b')
        canvas.create_text(left,bottom+17,text=xleft,anchor='w');canvas.create_text(right,bottom+17,text=xright,anchor='e')
        canvas.create_text(right,14,text=unit,anchor='ne',fill='#51647b')
        points=[]
        for i,v in enumerate(values):
            points.extend((left+i*(right-left)/max(1,len(values)-1),bottom-(max(low,min(high,v))-low)*(bottom-top)/(high-low)))
        if len(points)>=4:canvas.create_line(*points,fill='#147d92',width=2)

    def envelope(self):
        raw=Path(self.vector.get()).read_bytes()
        if len(raw)%4 or len(raw)>131072:raise ValueError('IQ 文件需为至多 32768 对 I16,Q16')
        v=list(struct.iter_unpack('<hh',raw));stride=max(1,len(v)//1000)
        power=[max(math.hypot(*x) for x in v[i:i+stride]) for i in range(0,len(v),stride)]
        self.draw(self.env,power,'装载的 IQ 文件包络（输入参考，非硬件采样回读）','码值','0 µs',f'{len(v)/100:.2f} µs')

    def show_update(self,u):
        r=u['record'];b=u.get('latest_burst');meta=u.get('metadata')
        burst_flags=('、'.join('采集停止时截断' if f=='CAPTURE_TRUNCATED' else f for f in b['flags']) or '完整') if b else ''
        burst_text=(f"最近突发长度 {b['length_samples']} 对 IQ / {b['length_us']:.2f} µs  |  突发状态 {burst_flags}" if b else '尚无突发记录')
        final_text=(f"\n采集核验：{'通过' if meta.get('capture_complete') else '失败'}  |  UDP 缺包 {meta.get('udp_missing_packet_count', '?')}  |  硬件错误 {meta.get('error_status', '?')}  |  最大发布延迟 {meta.get('hardware_max_publish_latency_cycles', 0)/100:.2f} µs" if meta else '')
        self.metrics.set(
          f"RMS {r['rms_codes']:.3f}  峰值 {r['peak_codes']:.3f}  |  峰频率 {r['peak_hz']/1e6:.6f} MHz\n"
          f"99% 带宽 {r['bandwidth_hz']/1e6:.6f} MHz  中心 {r['bandcenter_hz']/1e6:.6f} MHz  |  延迟 {r['latency_us']:.2f} µs\n"
          f"窗口 {r['id']}  已收频域 {u['frequency_records']} / 突发 {u['burst_records']}  |  标志 {', '.join(r['flags']) or '无'}\n{burst_text}{final_text}")
        shot=u.get('snapshot')
        if shot:
            peak=max(shot['power'],default=0)
            db=[10*math.log10(max(x,1)/max(peak,1)) if x else -100 for x in shot['power']]
            self.draw(self.spec,db,f"硬件功率频谱 / 窗口 {shot['window_id']}",'dB / 本快照峰值','−50 MHz','+50 MHz',(-100,0))

    def start(self):
        if self.worker and self.worker.is_alive():return
        try:
            seconds=float(self.seconds.get())
            if not 0<seconds<=3600:raise ValueError('持续时间应在 0–3600 秒之间')
            self.envelope()
        except Exception as e:messagebox.showerror('配置错误',str(e));return
        self.stop_event.clear();self.start_button.state(['disabled'])
        out=ROOT/'captures'/time.strftime('%Y%m%d_%H%M%S')
        args=SimpleNamespace(board=self.board.get(),port=5001,vector=self.vector.get(),out=str(out),
            window=self.window.get(),cyclic=True,seconds=seconds,stop_event=self.stop_event,
            on_update=lambda u:self.messages.put(('update',u)))
        self.status.set(f'正在连接、装载并读回验证 IQ 文件；结果将保存到 {out}')
        def run():
            try:capture(args);self.messages.put(('done',f'采集完整性检查通过：{out}'))
            except Exception as e:self.messages.put(('error',f'{e}；已接收结果保存于 {out}'))
        self.worker=threading.Thread(target=run,daemon=True);self.worker.start()

    def open_capture(self):
        if self.worker and self.worker.is_alive():return
        directory=filedialog.askdirectory()
        if not directory:return
        self.load_capture(directory)

    def load_capture(self,directory):
        try:
            d=Path(directory);f=d/'frequency.bin';f=f if f.exists() else d/'FREQ.BIN'
            raw=f.read_bytes()
            if not raw or len(raw)%128:raise ValueError('频域记录缺失或截断')
            b=d/'burst.bin';b=b if b.exists() else d/'BURST.BIN'
            latest_burst=None
            if b.exists() and b.stat().st_size:
                if b.stat().st_size%64:raise ValueError('突发记录截断')
                with b.open('rb') as stream:stream.seek(-64,2);latest_burst=decode_record(stream.read(64),'burst')
            meta=json.loads((d/'capture.json').read_text()) if (d/'capture.json').exists() else None
            if meta and meta.get('vector') and Path(meta['vector']).exists():self.vector.set(meta['vector'])
            shot=None
            if (d/'snapshot.json').exists():shot=json.loads((d/'snapshot.json').read_text())
            elif (d/'SNAP.BIN').exists():
                meta=json.loads((d/'META.JSON').read_text());shot=dict(window_id=meta['snapshot_window'],power=list(struct.unpack('<1024Q',(d/'SNAP.BIN').read_bytes())))
            self.show_update(dict(record=decode_record(raw[-128:],'frequency'),snapshot=shot,
                latest_burst=latest_burst,metadata=meta,
                frequency_records=len(raw)//128,burst_records=b.stat().st_size//64 if b.exists() else 0))
            self.status.set(f'离线查看：{d}；数据来源以该目录的 META.JSON / capture.json 为准。')
            self.envelope()
        except Exception as e:messagebox.showerror('读取失败',str(e))

    def poll(self):
        while not self.messages.empty():
            kind,data=self.messages.get()
            if kind=='update':self.show_update(data);self.status.set('正在接收硬件结果；显示刷新不等于输入采样速率。')
            else:self.status.set(data);self.start_button.state(['!disabled'])
        self.root.after(150,self.poll)

    def close(self):
        if self.worker and self.worker.is_alive():
            self.stop_event.set();self.status.set('正在请求完整窗口停止并保存数据，请等待采集结束。');return
        self.root.destroy()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--capture',type=Path)
    args=parser.parse_args()
    enable_dpi_awareness();root=tk.Tk();app=Monitor(root)
    if args.capture:root.after(200,lambda:app.load_capture(args.capture))
    root.mainloop()
