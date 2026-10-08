"""Tk desktop monitor; uses hardware results and labels replay input explicitly."""
from pathlib import Path
from types import SimpleNamespace
import json, math, queue, struct, threading, time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from iq_client import capture,decode_record,cycles_to_us,validate_detector,LENGTH_SEMANTICS
from threshold_config import resolve as resolve_threshold
from build_rates import SAMPLE_RATE_HZ
import monitor_view
ROOT=Path(__file__).resolve().parents[1]

def enable_dpi_awareness():
    import sys
    if sys.platform=='win32':
        import ctypes
        try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError,OSError):pass

class Monitor:
    def __init__(self,root):
        self.root=root;root.title('数字 IQ 信号分析 | Zybo Z7-20')
        root.geometry(f'{min(1240,root.winfo_screenwidth()-80)}x{min(920,root.winfo_screenheight()-100)}');root.minsize(900,720)
        self.messages=queue.Queue();self.worker=None;self.stop_event=threading.Event()
        self.board=tk.StringVar(value='192.168.1.10')
        self.vector=tk.StringVar(value=str(ROOT/'data/replay_vectors/qpsk_sps4.bin'))
        self.window=tk.StringVar(value='hann');self.seconds=tk.StringVar(value='10')
        self.detector=tk.StringVar(value='threshold');self.gap_min=tk.StringVar(value='32')
        self.threshold_profile=tk.StringVar(value='legacy');self.threshold_policy=tk.StringVar(value='fixed')
        self.quiet_samples=tk.StringVar(value='1024')
        self.threshold_values={name:tk.StringVar(value='') for name in ('ton','toff','kon','koff')}
        self.cyclic=tk.BooleanVar(value=True)
        self.sample_rate_hz=SAMPLE_RATE_HZ
        self.status=tk.StringVar(value='就绪：选择 IQ 文件，确认采集设置，然后开始采集；也可打开已有记录。')
        self.metrics=tk.StringVar(value='等待测量。全部幅度、包络长度、频率、带宽、延迟和核验信息将在此显示。')
        self.view_mode='idle';self._last_update=None
        self.capture_path=None
        monitor_view.build(self)
        root.after(150,self.poll);root.protocol('WM_DELETE_WINDOW',self.close)

    def choose_vector(self):
        p=filedialog.askopenfilename(filetypes=[('IQ binary','*.bin')])
        if p:
            self.vector.set(p)
            try:self.envelope()
            except Exception as error:messagebox.showerror('输入文件错误',str(error))

    def request_stop(self):
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self.status.set('正在等待完整窗口结束并保存记录，请勿断电。')

    def detector_selected(self):
        if self.detector.get()=='digital-zero':
            self.threshold_profile.set('legacy');self.threshold_policy.set('fixed')
            for value in self.threshold_values.values():value.set('')

    def copy_details(self):
        text=self.metrics.get()
        if self._last_update:text+='\n\n'+json.dumps(self._last_update,ensure_ascii=False,indent=2)
        self.root.clipboard_clear();self.root.clipboard_append(text)
        self.status.set('已复制全部测量信息和原始字段。')

    def set_busy(self,busy):
        self.start_button.state(['disabled'] if busy else ['!disabled'])
        self.stop_button.state(['!disabled'] if busy else ['disabled'])
        for widget,state in self.config_widgets:widget.configure(state='disabled' if busy else state)


    def draw(self,canvas,values,title,unit,xleft,xright,fixed=None):
        canvas._last_plot=(values,title,unit,xleft,xright,fixed)
        canvas.delete('all');w=max(canvas.winfo_width(),300);h=canvas.winfo_height()
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
        if not raw or len(raw)%4 or len(raw)>131072:raise ValueError('IQ 文件需包含 1～32768 对 I16,Q16')
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
        if b:
            self.metrics.set(self.metrics.get()+f"\n包络起止 [{b['start_sample']}, {b['end_sample_exclusive']})；包络 RMS {b['rms_codes']:.3f} / 峰值 {b['peak_codes']:.3f}")
        if meta:
            self.metrics.set(self.metrics.get()+f"\n构建 ID：{meta.get('build_id','未记录')}  |  FFT 时钟 {meta.get('fft_clock_hz','未记录')} Hz  |  时间戳时钟 {meta.get('timestamp_clock_hz','未记录')} Hz"
                +f"\n吞吐计数守恒：{meta.get('throughput_conservation_valid','未记录')}；详细计数见原始字段。")
        if self.capture_path:self.metrics.set(self.metrics.get()+f'\n记录目录：{self.capture_path}')
        monitor_view.update(self,u)
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
        self.stop_event.clear();self.set_busy(True)
        self.view_mode='live'
        monitor_view.reset(self)
        self.connection_note.set('连接与装载中…')
        out=ROOT/'captures'/(time.strftime('%Y%m%d_%H%M%S')+f'_{time.time_ns()%1000000000:09d}')
        self.capture_path=out
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
            vector_path=Path(meta['vector']) if meta and meta.get('vector') else None
            if vector_path and not vector_path.is_file():
                # The versioned evidence archive retains its original absolute metadata.
                alternatives=[d/'vectors'/vector_path.name,d.parent/'vectors'/vector_path.name,d.parent.parent/'vectors'/vector_path.name]
                vector_path=next((p for p in alternatives if p.is_file()),None)
            self.vector.set(str(vector_path) if vector_path and vector_path.is_file() else '')
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
            self.view_mode='offline';self.capture_path=d
            monitor_view.reset(self)
            record=decode_record(raw[-128:],'frequency')
            self.window.set(record['window'])
            if meta and 'cyclic' in meta:self.cyclic.set(bool(meta['cyclic']))
            self.show_update(dict(record=record,snapshot=shot,
                latest_burst=latest_burst,metadata=meta,
                frequency_records=len(raw)//128,burst_records=b.stat().st_size//64 if b.exists() else 0))
            self.status.set(f'离线查看：{d}；数据来源以该目录的 META.JSON / capture.json 为准。')
            if vector_path and vector_path.is_file():self.envelope()
            else:
                self.env.delete('all')
                if hasattr(self.env,'_last_plot'):del self.env._last_plot
                self.env.create_text(20,22,anchor='nw',text='原始 IQ 文件不可用；已显示板端测量记录，未使用其他输入代替。',fill='#5c7080')
        except Exception as e:messagebox.showerror('读取失败',str(e))

    def poll(self):
        while not self.messages.empty():
            kind,data=self.messages.get()
            if kind=='update':self.show_update(data);self.status.set('正在接收硬件结果；显示刷新不等于输入采样速率。')
            else:
                self.status.set(data);self.set_busy(False)
                self.connection_note.set('采集完成 · 请查看核验结果' if kind=='done' else '采集异常 · 请查看错误信息')
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
