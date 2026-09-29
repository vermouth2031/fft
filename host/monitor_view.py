"""Presentation layer for the desktop monitor; acquisition stays in iq_client."""
import json
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

BG = '#eef3f7'
INK = '#193448'
MUTED = '#5c7080'
ACCENT = '#147c87'


def scroll_page(app, page, minimum_height=None):
    """Keep content reachable on smaller displays, including Windows DPI scaling."""
    viewport = tk.Canvas(page, bg=BG, highlightthickness=0, height=220)
    scrollbar = ttk.Scrollbar(page, command=viewport.yview)
    viewport.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right', fill='y')
    viewport.pack(fill='both', expand=True)
    content = ttk.Frame(viewport)
    embedded = viewport.create_window(0, 0, window=content, anchor='nw')
    content.bind('<Configure>', lambda e: viewport.configure(scrollregion=viewport.bbox('all')))
    def resize(event):
        options = dict(width=event.width)
        if minimum_height:
            options['height'] = max(minimum_height, event.height)
        viewport.itemconfigure(embedded, **options)
    viewport.bind('<Configure>', resize)
    def scroll(event):
        if app.tabs.select() == str(page):
            viewport.yview_scroll(-1 if event.delta > 0 else 1, 'units')
    app.root.bind('<MouseWheel>', scroll, add='+')
    return content, viewport


def build(app):
    root = app.root
    root.configure(background=BG)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Microsoft YaHei UI', 10), background=BG, foreground=INK)
    style.configure('TButton', padding=(12, 7))
    style.configure('Accent.TButton', background=ACCENT, foreground='white', font=('Microsoft YaHei UI', 10, 'bold'))
    style.map('Accent.TButton', background=[('disabled', '#a4b9bf'), ('active', '#116875')])
    style.configure('White.TFrame', background='white')
    style.configure('White.TLabel', background='white')
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('TNotebook', background=BG, borderwidth=0)
    style.configure('TNotebook.Tab', padding=(18, 9))
    style.map('TNotebook.Tab', background=[('selected', 'white')], foreground=[('selected', ACCENT)])
    style.configure('Treeview', rowheight=29, background='white', fieldbackground='white')
    style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 10, 'bold'), padding=7)
    app.config_widgets = []
    app.card_values = {}
    app.card_notes = {}
    app.connection_note = tk.StringVar(value='尚未采集 · 等待板卡数据')
    app.record_note = tk.StringVar(value='输入为板内预装载回放；结果以实际记录为准。')

    shell = ttk.Frame(root, padding=(18, 12, 18, 10))
    shell.pack(fill='both', expand=True)
    header = ttk.Frame(shell); header.pack(fill='x', pady=(0, 9))
    ttk.Label(header, text='数字 IQ 信号分析', font=('Microsoft YaHei UI', 16, 'bold')).pack(side='left')
    ttk.Label(header, text='Zybo Z7-20', style='Muted.TLabel').pack(side='left', padx=18)
    ttk.Label(header, textvariable=app.connection_note, foreground=ACCENT,font=('Microsoft YaHei UI',9)).pack(side='right')

    toolbar = ttk.Frame(shell, style='White.TFrame', padding=12); toolbar.pack(fill='x')
    for col in (1,): toolbar.columnconfigure(col, weight=1)
    ttk.Label(toolbar, text='输入 IQ 文件', style='White.TLabel').grid(row=0, column=0, sticky='w', padx=(0,10))
    path = ttk.Entry(toolbar, textvariable=app.vector)
    path.grid(row=0, column=1, sticky='ew', padx=(0,8)); app.config_widgets.append((path, 'normal'))
    choose = ttk.Button(toolbar, text='选择文件…', command=app.choose_vector)
    choose.grid(row=0, column=2); app.config_widgets.append((choose, 'normal'))
    app.open_button = ttk.Button(toolbar, text='打开已有记录…', command=app.open_capture)
    app.open_button.grid(row=0, column=3, padx=(8,0)); app.config_widgets.append((app.open_button,'normal'))
    controls = ttk.Frame(toolbar, style='White.TFrame'); controls.grid(row=1,column=0,columnspan=4,sticky='ew',pady=(10,0))
    ttk.Label(controls, text='板卡 IP', style='White.TLabel').pack(side='left')
    ip = ttk.Entry(controls,textvariable=app.board,width=16);ip.pack(side='left',padx=(8,18));app.config_widgets.append((ip,'normal'))
    app.start_button=ttk.Button(controls,text='开始采集',style='Accent.TButton',command=app.start)
    app.start_button.pack(side='left')
    app.stop_button=ttk.Button(controls,text='窗口边界停止',command=app.request_stop)
    app.stop_button.pack(side='left',padx=8);app.stop_button.state(['disabled'])
    app.settings_hint=tk.StringVar()
    ttk.Label(toolbar,textvariable=app.settings_hint,style='White.TLabel',foreground=MUTED,font=('Microsoft YaHei UI',9)).grid(row=2,column=0,columnspan=4,sticky='w',pady=(6,0))

    cards=ttk.Frame(shell);cards.pack(fill='x',pady=(12,4))
    definitions=[('amplitude','信号幅度','RMS / 数字码值'),('length','帧长度','突发包络 / µs'),
                 ('frequency','频点','谱峰 / MHz'),('bandwidth','带宽','99% 占用带宽 / MHz')]
    for col,(key,title,caption) in enumerate(definitions):
        cards.columnconfigure(col,weight=1,uniform='metric')
        frame=ttk.Frame(cards,style='White.TFrame',padding=(13,10))
        frame.grid(row=0,column=col,sticky='nsew',padx=(0,8) if col<3 else 0)
        ttk.Label(frame,text=title,style='White.TLabel',font=('Microsoft YaHei UI',10,'bold')).pack(anchor='w')
        value=tk.StringVar(value='—');note=tk.StringVar(value='等待测量')
        app.card_values[key]=value;app.card_notes[key]=note
        value_label=ttk.Label(frame,textvariable=value,style='White.TLabel',foreground=ACCENT,font=('Microsoft YaHei UI',19,'bold'))
        value_label.pack(anchor='w',pady=(2,0))
        ttk.Label(frame,text=caption,style='White.TLabel',foreground=MUTED,font=('Microsoft YaHei UI',8)).pack(anchor='w')
        note_label=ttk.Label(frame,textvariable=note,style='White.TLabel',foreground=MUTED,font=('Microsoft YaHei UI',8))
        note_label.pack(anchor='w')
        def resize_metric(event=None,frame=frame,label=value_label,value=value,note=note_label):
            available=max(80,frame.winfo_width()-28)
            for size in range(19,9,-1):
                if tkfont.Font(root=root,family='Microsoft YaHei UI',size=size,weight='bold').measure(value.get())<=available:break
            label.configure(font=('Microsoft YaHei UI',size,'bold'))
            note.configure(wraplength=available)
        frame.bind('<Configure>',resize_metric)
        value.trace_add('write',lambda *args,callback=resize_metric:callback())
    record_label=ttk.Label(shell,textvariable=app.record_note,style='Muted.TLabel',wraplength=1050,font=('Microsoft YaHei UI',9))
    record_label.pack(anchor='w',pady=(2,8))

    footer=ttk.Label(shell,textvariable=app.status,style='Muted.TLabel',wraplength=1050,font=('Microsoft YaHei UI',9))
    footer.pack(side='bottom',fill='x',pady=(9,0))
    app.status_label=footer
    app.tabs=ttk.Notebook(shell,height=220);app.tabs.pack(fill='both',expand=True)
    app.pages={}
    for key,title in [('plots','波形与频谱'),('requirements','赛题指标'),('settings','采集设置'),('details','数据与校验')]:
        page=ttk.Frame(app.tabs,padding=12);app.tabs.add(page,text=title);app.pages[key]=page
    plots,app.plots_viewport=scroll_page(app,app.pages['plots'],minimum_height=350)
    plots.columnconfigure(0,weight=1)
    for row in (0,1):plots.rowconfigure(row,weight=1,uniform='plot')
    app.env=tk.Canvas(plots,height=145,bg='white',highlightthickness=0)
    app.spec=tk.Canvas(plots,height=170,bg='white',highlightthickness=0)
    app.env.grid(row=0,column=0,sticky='nsew',pady=(0,5));app.spec.grid(row=1,column=0,sticky='nsew',pady=(5,0))
    for canvas,prompt in [(app.env,'选择 IQ 文件后显示输入包络'),(app.spec,'采集或打开记录后显示板端频谱')]:
        canvas.create_text(20,22,text=prompt,anchor='nw',fill=MUTED,font=('Microsoft YaHei UI',11))
        canvas.bind('<Configure>',lambda e:app.draw(e.widget,*e.widget._last_plot) if hasattr(e.widget,'_last_plot') else None)
    plot_note=ttk.Label(plots,text='输入包络来自装载文件；频谱为板端每 8 个 bin 取最大值的快照，99% 带宽使用完整 8192 点计算。',style='Muted.TLabel',font=('Microsoft YaHei UI',9),wraplength=800)
    plot_note.grid(row=2,column=0,sticky='w',pady=(8,0))
    plots.bind('<Configure>',lambda e:plot_note.configure(wraplength=max(300,e.width-12)),add='+')

    page,app.requirements_viewport=scroll_page(app,app.pages['requirements'])
    ttk.Label(page,text='按当前记录对照赛题数值要求',font=('Microsoft YaHei UI',13,'bold')).pack(anchor='w',pady=(0,8))
    app.requirements=ttk.Treeview(page,columns=('item','target','actual','result'),show='headings',height=5)
    for key,title,width in [('item','指标',170),('target','题面要求',170),('actual','当前记录',240),('result','数值对照',160)]:
        app.requirements.heading(key,text=title);app.requirements.column(key,width=width,minwidth=110,stretch=True)
    app.requirements.pack(fill='x')
    for key,title,target in [('bits','I / Q 位宽','每路 ≥ 12 bit'),('rate','IQ 数据速率','≥ 100 MSPS'),('fft','FFT 点数','≥ 8192 点'),
                             ('latency','分析处理时间','≤ 2000 µs'),('width','数字 IQ 带宽','MHz，越高越好')]:
        app.requirements.insert('', 'end',iid=key,values=(title,target,'—','等待记录'))
    ttk.Label(page,text='计时从窗口首个 IQ 被 PL 接受到分析完成，不含电脑上传、网络往返和绘图。\n'
              '当前输入为板内回放；位宽表示数字格式。帧长度是包络长度，谱峰不等于宽带调制载频。\n'
              '数值满足门槛不等于赛方认定或整套验收通过；采集完整性与数值参考核验见“数据与校验”。',
              style='Muted.TLabel',justify='left',wraplength=800).pack(anchor='w',pady=16)

    settings,viewport=scroll_page(app,app.pages['settings'])
    basic=ttk.LabelFrame(settings,text='常用采集参数',padding=14);basic.pack(fill='x',pady=(0,12))
    def field(parent,row,column,label,var,values=None,width=15):
        ttk.Label(parent,text=label).grid(row=row,column=column,sticky='w',padx=(0,8),pady=6)
        widget=(ttk.Combobox(parent,textvariable=var,values=values,state='readonly',width=width) if values
                else ttk.Entry(parent,textvariable=var,width=width))
        widget.grid(row=row,column=column+1,sticky='w',padx=(0,22),pady=6)
        app.config_widgets.append((widget,'readonly' if values else 'normal'));return widget
    field(basic,0,0,'分析窗',app.window,['rect','hann'])
    field(basic,0,2,'持续秒数（循环时）',app.seconds,width=9)
    cyclic=ttk.Checkbutton(basic,text='循环回放；取消后仅回放一次',variable=app.cyclic)
    cyclic.grid(row=1,column=0,columnspan=4,sticky='w',pady=6);app.config_widgets.append((cyclic,'normal'))
    detector=field(basic,2,0,'长度检测模式',app.detector,['threshold','digital-zero'])
    detector.bind('<<ComboboxSelected>>',lambda e:app.detector_selected())
    field(basic,2,2,'零间隔确认 / 点',app.gap_min,width=9)
    ttk.Label(basic,text='rect：矩形窗 / hann：Hann 窗；threshold：门限检测 / digital-zero：数字零背景测长。',style='Muted.TLabel',wraplength=690,font=('Microsoft YaHei UI',9)).grid(row=3,column=0,columnspan=4,sticky='w',pady=(6,0))
    advanced=ttk.LabelFrame(settings,text='高级门限参数 · 用于 threshold 模式',padding=14);advanced.pack(fill='x')
    profile=field(advanced,0,0,'门限档位',app.threshold_profile,['legacy','robust'])
    profile.bind('<<ComboboxSelected>>',lambda e:app.threshold_policy.set('quiet-prefix' if app.threshold_profile.get()=='robust' else 'fixed'))
    field(advanced,0,2,'门限策略',app.threshold_policy,['fixed','quiet-prefix'])
    field(advanced,1,0,'前导静默点数',app.quiet_samples,width=15)
    manual=ttk.Frame(advanced);manual.grid(row=2,column=0,columnspan=4,sticky='w')
    for col,name in enumerate(('ton','toff','kon','koff')):
        field(manual,0,col*2,name,app.threshold_values[name],width=9)
    ttk.Label(advanced,text='留空沿用档位。ton/toff 是 16 点能量门限，kon/koff 是开启/关闭确认点数。\n'
              'robust 为带噪档位；quiet-prefix 需要输入确有前导静默。切换到数字零模式会清除门限覆盖。',
              style='Muted.TLabel',justify='left',wraplength=690,font=('Microsoft YaHei UI',9)).grid(row=3,column=0,columnspan=4,sticky='w',pady=(6,0))
    app.settings_viewport=viewport

    details=app.pages['details']
    tools=ttk.Frame(details);tools.pack(fill='x',pady=(0,8))
    ttk.Label(tools,text='实际数据、状态与核验',font=('Microsoft YaHei UI',13,'bold')).pack(side='left')
    ttk.Button(tools,text='复制完整数据',command=app.copy_details).pack(side='right')
    sub=ttk.Notebook(details);sub.pack(fill='both',expand=True)
    summary=ttk.Frame(sub);raw=ttk.Frame(sub);sub.add(summary,text='全部测量信息');sub.add(raw,text='原始字段 / 元数据')
    app.detail_text=tk.Text(summary,wrap='word',font=('Microsoft YaHei UI',11),bg='white',fg=INK,relief='flat',padx=16,pady=12,state='disabled',height=8)
    scroll=ttk.Scrollbar(summary,command=app.detail_text.yview);app.detail_text.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right',fill='y');app.detail_text.pack(fill='both',expand=True)
    app.raw_text=tk.Text(raw,wrap='none',font=('Consolas',10),bg='white',fg=INK,relief='flat',state='disabled',height=8)
    sy=ttk.Scrollbar(raw,command=app.raw_text.yview);sx=ttk.Scrollbar(raw,orient='horizontal',command=app.raw_text.xview)
    app.raw_text.configure(yscrollcommand=sy.set,xscrollcommand=sx.set);sy.pack(side='right',fill='y');sx.pack(side='bottom',fill='x');app.raw_text.pack(fill='both',expand=True)
    app.metrics.trace_add('write',lambda *args:replace_text(app.detail_text,app.metrics.get()))
    replace_text(app.detail_text,app.metrics.get())
    def resize_root(event):
        if event.widget is root:
            footer.configure(wraplength=max(500,event.width-45))
            record_label.configure(wraplength=max(500,event.width-45))
    root.bind('<Configure>',resize_root)
    def hint(*args):
        app.settings_hint.set(f"{'循环 '+app.seconds.get()+' 秒' if app.cyclic.get() else '单次回放'}  ·  {app.window.get()}  ·  参数见“采集设置”")
    for var in (app.cyclic,app.seconds,app.window):var.trace_add('write',hint)
    hint()


def replace_text(widget,text):
    widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',text);widget.configure(state='disabled')


def reset(app):
    for value in app.card_values.values():value.set('—')
    for note in app.card_notes.values():note.set('等待本次测量')
    for key in app.requirements.get_children():
        values=list(app.requirements.item(key,'values'));values[2:]=['—','等待记录'];app.requirements.item(key,values=values)
    app.spec.delete('all')
    if hasattr(app.spec,'_last_plot'):del app.spec._last_plot
    app.spec.create_text(20,22,text='等待本次板端频谱快照',anchor='nw',fill=MUTED)
    app.metrics.set('等待本次记录；上一次测量已清空。')
    replace_text(app.raw_text,'等待本次记录。')
    app.record_note.set('正在建立本次采集；数值以新的板端记录为准。')
    app._last_update=None


def update(app,u):
    r=u['record'];b=u.get('latest_burst');meta=u.get('metadata') or {}
    app._last_update=u
    app.card_values['amplitude'].set(f"{r['rms_codes']:.3f}")
    app.card_notes['amplitude'].set(f"峰值 {r['peak_codes']:.3f}")
    app.card_values['length'].set(f"{b['length_us']:.2f}" if b else '—')
    app.card_notes['length'].set(f"{b['length_samples']} 对 IQ" if b else '尚无包络记录')
    app.card_values['frequency'].set(f"{r['peak_hz']/1e6:.6f}")
    app.card_notes['frequency'].set('最高谱线；非调制载频')
    app.card_values['bandwidth'].set(f"{r['bandwidth_hz']/1e6:.6f}")
    app.card_notes['bandwidth'].set(f"中心 {r['bandcenter_hz']/1e6:.6f} MHz")
    mode='离线记录' if app.view_mode=='offline' else ('采集完成' if meta else '实时记录')
    flags=', '.join(r['flags']) or '无'
    suffix='；包络未完整确认' if b and not(b.get('start_confirmed') and b.get('end_confirmed')) else ''
    app.record_note.set(f"{mode} · 窗口 {r['id']} · 已收频域 {u['frequency_records']} / 突发 {u['burst_records']} · PL 分析 {r['latency_us']:.2f} µs · 标志 {flags}{suffix}")
    app.connection_note.set('离线查看 · 不连接板卡' if app.view_mode=='offline' else ('采集结束 · 查看完整性结果' if meta else '正在接收板卡数据'))
    current = {'bits':('I16 / Q16','输入格式符合'),
               'rate':(f"{r['sample_rate_hz']/1e6:g} MSPS",'数值满足' if r['sample_rate_hz']>=100000000 else '未满足'),
               'fft':(f"{r['fft_length']} 点",'数值满足' if r['fft_length']>=8192 else '未满足'),
               'latency':(f"{r['latency_us']:.2f} µs（本窗口）",'数值满足' if 0<r['latency_us']<=2000 else '未满足'),
               'width':(f"{r['bandwidth_hz']/1e6:.6f} MHz",'未规定数值下限')}
    if meta.get('hardware_max_latency_cycles') is not None:
        maximum=meta['hardware_max_latency_cycles']*1e6/r['sample_rate_hz']
        current['latency']=(f'{maximum:.2f} µs（本次最大）','数值满足' if 0<maximum<=2000 else '未满足')
    for key,(value,result) in current.items():
        values=list(app.requirements.item(key,'values'));values[2:]=[value,result];app.requirements.item(key,values=values)
    replace_text(app.raw_text,json.dumps(u,ensure_ascii=False,indent=2))
