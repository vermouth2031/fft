"""Tk desktop monitor; uses hardware results and labels replay input explicitly."""
from pathlib import Path
from types import SimpleNamespace
import json, math, queue, struct, threading, time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from iq_client import capture,decode_record,cycles_to_us,validate_detector,LENGTH_SEMANTICS
from threshold_config import resolve as resolve_threshold
from build_rates import SAMPLE_RATE_HZ
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
        self.detector=tk.StringVar(value='threshold');self.gap_min=tk.StringVar(value='32')
        self.threshold_profile=tk.StringVar(value='legacy');self.threshold_policy=tk.StringVar(value='fixed')
        self.quiet_samples=tk.StringVar(value='1024')
        self.threshold_values={name:tk.StringVar(value='') for name in ('ton','toff','kon','koff')}
        self.cyclic=tk.BooleanVar(value=True)
        self.sample_rate_hz=SAMPLE_RATE_HZ
        form=ttk.Frame(root,padding=12);form.pack(fill='x')
        for col,(label,var,width) in enumerate([('板卡 IP',self.board,18),('持续秒数',self.seconds,8)]):
            ttk.Label(form,text=label).grid(row=0,column=col*2,padx=4)
            ttk.Entry(form,textvariable=var,width=width).grid(row=0,column=col*2+1)
        ttk.Combobox(form,textvariable=self.window,values=['rect','hann'],state='readonly',width=8).grid(row=0,column=4,padx=8)
        buttons=ttk.Frame(form);buttons.grid(row=1,column=0,columnspan=6,sticky='w',pady=8)
        self.start_button=ttk.Button(buttons,text='开始采集',command=self.start);self.start_button.pack(side='left',padx=4)
        ttk.Button(buttons,text='窗口边界停止',command=self.stop_event.set).pack(side='left',padx=4)
        ttk.Button(buttons,text='打开已有记录',command=self.open_capture).pack(side='left',padx=4)
        ttk.Checkbutton(buttons,text='循环回放（取消则仅回放一次）',variable=self.cyclic).pack(side='left',padx=12)
        ttk.Entry(form,textvariable=self.vector,width=65).grid(row=2,column=0,columnspan=5,pady=4,sticky='we')
        ttk.Button(form,text='选择 IQ 文件',command=self.choose_vector).grid(row=2,column=5,padx=8)
        detector_form=ttk.Frame(form);detector_form.grid(row=3,column=0,columnspan=6,sticky='w',pady=4)
        ttk.Label(detector_form,text='长度检测模式').pack(side='left',padx=4)
        ttk.Combobox(detector_form,textvariable=self.detector,values=['threshold','digital-zero'],state='readonly',width=14).pack(side='left')
        ttk.Label(detector_form,text='零间隔确认点数').pack(side='left',padx=8)
        ttk.Entry(detector_form,textvariable=self.gap_min,width=7).pack(side='left')
        ttk.Label(detector_form,text='threshold：门限突发；digital-zero：数字零背景波形').pack(side='left',padx=8)
        threshold_form=ttk.Frame(form);threshold_form.grid(row=4,column=0,columnspan=6,sticky='w',pady=4)
        ttk.Label(threshold_form,text='门限档位').pack(side='left',padx=4)
        profile_box=ttk.Combobox(threshold_form,textvariable=self.threshold_profile,values=['legacy','robust'],state='readonly',width=9)
        profile_box.pack(side='left')
        profile_box.bind('<<ComboboxSelected>>',lambda e:self.threshold_policy.set('quiet-prefix' if self.threshold_profile.get()=='robust' else 'fixed'))
        ttk.Combobox(threshold_form,textvariable=self.threshold_policy,values=['fixed','quiet-prefix'],state='readonly',width=13).pack(side='left',padx=6)
        ttk.Label(threshold_form,text='前导静默点数').pack(side='left')
        ttk.Entry(threshold_form,textvariable=self.quiet_samples,width=7).pack(side='left',padx=4)
        ttk.Label(threshold_form,text='quiet-prefix 要求输入确有前导静默；robust 为带噪档位').pack(side='left')
        manual_form=ttk.Frame(form);manual_form.grid(row=5,column=0,columnspan=6,sticky='w',pady=4)
        for name in ('ton','toff','kon','koff'):
            ttk.Label(manual_form,text=name).pack(side='left',padx=4)
            ttk.Entry(manual_form,textvariable=self.threshold_values[name],width=11).pack(side='left')
        ttk.Label(manual_form,text='留空使用档位参数；ton/toff 为16点能量，kon/koff 为点数').pack(side='left',padx=6)
        form.columnconfigure(4,weight=1)
        self.status=tk.StringVar(value='等待连接。输入为板内预装载回放，I/Q 各 16bit；采集后显示实际速率与配置。')
        status_label=ttk.Label(root,textvariable=self.status,padding=12,wraplength=1050);status_label.pack(fill='x')
        root.bind('<Configure>',lambda e:status_label.configure(wraplength=max(500,e.width-30)) if e.widget is root else None)
        self.metrics=tk.StringVar(value='幅度、波形长度、频率、99% 带宽和处理延迟将在采集后显示。长度测量不识别通信协议帧。')
        ttk.Label(root,textvariable=self.metrics,padding=12,font=('Microsoft YaHei UI',11)).pack(fill='x')
        ttk.Label(root,text='频谱：PL 每 8 个 bin 取最大值的显示快照；99% 带宽由完整 8192 点计算。',padding=8).pack(side='bottom',fill='x')
        plots=ttk.Frame(root);plots.pack(fill='both',expand=True,padx=14,pady=6)
        plots.columnconfigure(0,weight=1)
        for row in (0,1):plots.rowconfigure(row,weight=1,uniform='plots')
        self.env=tk.Canvas(plots,height=140,bg='#f7f9fc',highlightthickness=0);self.env.grid(row=0,column=0,sticky='nsew',pady=(0,6))
        self.spec=tk.Canvas(plots,height=180,bg='#f7f9fc',highlightthickness=0);self.spec.grid(row=1,column=0,sticky='nsew',pady=(6,0))
        for canvas in (self.env,self.spec):
            canvas.bind('<Configure>',lambda e:self.draw(e.widget,*e.widget._last_plot) if hasattr(e.widget,'_last_plot') else None)
        root.after(150,self.poll);root.protocol('WM_DELETE_WINDOW',self.close)

    def choose_vector(self):
        p=filedialog.askopenfilename(filetypes=[('IQ binary','*.bin')])
        if p:self.vector.set(p)

    def draw(self,canvas,values,title,unit,xleft,xright,fixed=None):
        canvas._last_plot=(values,title,unit,xleft,xright,fixed)
        canvas.delete('all');w=max(canvas.winfo_width(),700);h=canvas.winfo_height()
        if h<110:
            canvas.create_text(16,14,anchor='nw',text='放大窗口以查看完整图形',fill='#51647b')
            return
        canvas.create_text(16,14,anchor='nw',text=title,fill='#193353',font=('Microsoft YaHei UI',10))
        left,top,right,bottom=90,45,w-24,h-35
        low,high=fixed or (min(values,default=0),max(values,default=1))
        if high==low:low=0;high=max(1,high)
        ticks=3 if h<200 else 5
        for j in range(ticks):
            y=top+(bottom-top)*j/(ticks-1);value=high-(high-low)*j/(ticks-1)
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
        self.draw(self.env,power,'装载的 IQ 文件包络（输入参考，非硬件采样回读）','码值','0 µs',f'{cycles_to_us(len(v),self.sample_rate_hz):.2f} µs')

    def show_update(self,u):
        r=u['record'];b=u.get('latest_burst');meta=u.get('metadata')
        self.sample_rate_hz=r['sample_rate_hz']
        flag_labels={'CAPTURE_TRUNCATED':'结束未确认／停止截断','DETECTOR_TIMEOUT':'长度上限分段',
            'START_UNCONFIRMED':'起点未确认','DIGITAL_ZERO':'数字零背景'}
        burst_flags=('、'.join(flag_labels.get(f,f) for f in b['flags']) or '门限突发已确认') if b else ''
        burst_text=(f"{b['length_semantics']} {b['length_samples']} 对 IQ / {b['length_us']:.2f} µs  |  状态 {burst_flags}" if b else '尚无波形长度记录')
        final_text=''
        if meta:
            rate=meta.get('sample_rate_hz') or self.sample_rate_hz
            reference=meta.get('numerical_reference_validation',{}).get('status','NOT_RUN')
            reference_text={'PASS':'通过','FAIL':'失败','NOT_RUN':'未执行（与采集完整性分开）'}.get(reference,reference)
            final_text=(f"\n采集完整性：{'通过' if meta.get('capture_complete') else '失败'}  |  UDP 缺包 {meta.get('udp_missing_packet_count', '?')}  |  硬件错误 {meta.get('error_status', '?')}  |  最大发布延迟 {cycles_to_us(meta.get('hardware_max_publish_latency_cycles',0),rate):.2f} µs"
                f"\n数值参考核验：{reference_text}  |  波形长度不等于协议帧识别")
            if meta.get('applied_detector'):
                d=meta['applied_detector']
                final_text+=f"\n实际门限 ton/toff={d['ton']}/{d['toff']}，确认 kon/koff={d['kon']}/{d['koff']} 点"
        self.metrics.set(
          f"RMS {r['rms_codes']:.3f}  峰值 {r['peak_codes']:.3f}  |  峰频率 {r['peak_hz']/1e6:.6f} MHz\n"
          f"99% 带宽 {r['bandwidth_hz']/1e6:.6f} MHz  带宽中心 {r['bandcenter_hz']/1e6:.6f} MHz  |  PL 分析延迟 {r['latency_us']:.2f} µs\n"
          f"板内回放 I16/Q16  |  {r['sample_rate_hz']/1e6:g} M 对 IQ/秒  |  FFT {r['fft_length']} 点  |  窗 {r['window']}\n"
          f"窗口 {r['id']}  已收频域 {u['frequency_records']} / 突发 {u['burst_records']}  |  标志 {', '.join(r['flags']) or '无'}\n{burst_text}{final_text}")
        shot=u.get('snapshot')
        if shot:
            peak=max(shot['power'],default=0)
            db=[10*math.log10(max(x,1)/max(peak,1)) if x else -100 for x in shot['power']]
            half=self.sample_rate_hz/2e6
            self.draw(self.spec,db,f"硬件功率频谱 / 窗口 {shot['window_id']}",'dB / 本快照峰值',f'−{half:g} MHz',f'+{half:g} MHz',(-100,0))

    def start(self):
        if self.worker and self.worker.is_alive():return
        try:
            seconds=float(self.seconds.get())
            if not 0<seconds<=3600:raise ValueError('持续时间应在 0–3600 秒之间')
            gap_min=int(self.gap_min.get());validate_detector(self.detector.get(),gap_min)
            threshold_options=dict(threshold_profile=self.threshold_profile.get(),threshold_policy=self.threshold_policy.get(),
                quiet_samples=int(self.quiet_samples.get()),**{k:int(v.get()) if v.get().strip() else None for k,v in self.threshold_values.items()})
            resolve_threshold(SimpleNamespace(detector=self.detector.get(),gap_min=gap_min,**threshold_options),Path(self.vector.get()).read_bytes())
            self.envelope()
        except Exception as e:messagebox.showerror('配置错误',str(e));return
        self.stop_event.clear();self.start_button.state(['disabled'])
        out=ROOT/'captures'/time.strftime('%Y%m%d_%H%M%S')
        args=SimpleNamespace(board=self.board.get(),port=5001,vector=self.vector.get(),out=str(out),
            window=self.window.get(),cyclic=self.cyclic.get(),seconds=seconds,stop_event=self.stop_event,
            detector=self.detector.get(),gap_min=gap_min,
            **threshold_options,
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
            metadata_path=next((d/name for name in ('capture.json','META.JSON') if (d/name).exists()),None)
            meta=json.loads(metadata_path.read_text(encoding='utf-8-sig')) if metadata_path else None
            if meta and meta.get('vector') and Path(meta['vector']).exists():self.vector.set(meta['vector'])
            if meta and meta.get('detector_mode') in LENGTH_SEMANTICS:self.detector.set(meta['detector_mode'])
            if meta and meta.get('gap_min') is not None:self.gap_min.set(str(meta['gap_min']))
            request=(meta or {}).get('threshold_request',{})
            profile=request.get('profile','legacy');policy=request.get('policy','fixed')
            explicit=profile=='explicit'
            self.threshold_profile.set(profile if profile in ('legacy','robust') else 'legacy')
            self.threshold_policy.set(policy if policy in ('fixed','quiet-prefix') else 'fixed')
            self.quiet_samples.set(str(request.get('quiet_interval',[0,1024])[1]))
            requested=(meta or {}).get('applied_detector',{}) if explicit else request.get('requested_parameters',{})
            for key,value in self.threshold_values.items():
                setting=requested.get(key)
                value.set(str(setting) if setting is not None and self.detector.get()=='threshold' else '')
            shot=None
            if (d/'snapshot.json').exists():shot=json.loads((d/'snapshot.json').read_text())
            elif (d/'SNAP.BIN').exists():
                sd_meta=json.loads((d/'META.JSON').read_text());shot=dict(window_id=sd_meta['snapshot_window'],power=list(struct.unpack('<1024Q',(d/'SNAP.BIN').read_bytes())))
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
