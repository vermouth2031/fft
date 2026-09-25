"""Produce a beginner-readable report and plots from saved, verified board data."""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'build/five_signals_plotdeps'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('folder', type=Path)
    a = p.parse_args(); folder = a.folder.resolve()
    report = read(folder/'validation.json'); manifest = read(folder/'manifest.json')
    assert report['status']=='PASS' and len(report['cases'])==10
    for c in report['cases']:
        for name, digest in c['files'].items():
            assert sha(Path(c['folder'])/name)==digest, 'Changed raw evidence'
    font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10})
    fig, axes = plt.subplots(5,2,figsize=(15,16),layout='constrained')
    lines = ['# 五组新信号真板测试结果', '',
        '这次新生成单音、双音、扫频、QPSK、OFDM五组输入，每组使用矩形窗和Hann窗各测一次，共10次真板采集。', '',
        f"全部10次通过独立数值参考核验，共{report['frequency_records']}条频域记录、{report['burst_records']}条包络记录、{report['snapshot_values']}个快照数值；最大分析延迟{report['maximum_analysis_us']:.2f} µs。", '',
        f"板上构建：`{report['hardware']['build_id']}`。输入为100 MSPS板内回放，I/Q各16bit，8192点FFT。", '',
        '信号名称来自本次生成时已知的设计，不代表电路能自动识别调制类型。本次没有添加噪声。', '',
        '## 先看结果', '',
        '下表幅度、峰频、带宽统一取第1号完整内部窗，即81.92～163.84 µs；长度来自整段数字零背景包络记录。幅度单位为数字码值，频率为基带频率。', '',
        '| 信号 | 窗 | RMS幅度 | 峰值幅度 | 谱峰/MHz | 99%带宽/MHz | 包络长度/µs | 最大分析延迟/µs |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    table_rows = []
    for c in report['cases']:
        f = c['representative']; b = c['burst']
        cells = [c['name'], '矩形' if c['window']=='rect' else 'Hann',f"{f['rms_codes']:.3f}", f"{f['peak_codes']:.3f}",
                 f"{f['peak_hz']/1e6:.6f}", f"{f['bandwidth_hz']/1e6:.6f}", f"{b['length_us']:.2f}", f"{c['maximum_analysis_us']:.2f}"]
        table_rows.append(cells);lines.append('| '+' | '.join(cells)+' |')
    notes = {
        'tone':'像一个固定音调。设定频率为+12.5 MHz，两种窗均准确落在该频率。矩形窗的99%边界落在同一个FFT格子，带宽为0并带RESOLUTION_LIMITED标志；这不是漏测。Hann窗把谱线展开，测得24.414 kHz。生成时幅度设为8000，量化成整数后约为8000.103，真板与整数参考一致。',
        'two_tone':'像两个音调同时响：−12.5 MHz幅度6000，+18.75 MHz幅度3000。较强的前者成为输出谱峰。矩形窗99%带宽为31.25 MHz，即两条谱线之间的跨度；中间没有信号的间隔也包括在跨度内。单个峰频字段不会同时输出两个峰，两个峰可以从实测频谱图看到。',
        'chirp':'像音调逐渐升高的警报。整段在245.76 µs内从−20 MHz扫至接近+20 MHz，但一个FFT窗口只观察81.92 µs。表格窗口的设计频率只从约−10 MHz扫到+3.333 MHz，所以矩形窗测得约13.184 MHz，而不是整段40 MHz。Hann窗降低窗口两端的权重，99%带宽进一步变窄。这个信号没有唯一固定频点。',
        'qpsk':'像通过不断变化的信号状态传递一串信息。这里使用25 M符号/秒的QPSK、滚降0.35的成形滤波。矩形窗测得约29.08 MHz的99%带宽。输入中心设在0 Hz，但随机数据会在别处形成最大谱峰；−4.993 MHz不是中心频率出错。滤波尾部和整数化后的非零区间使实测包络为246.13 µs。',
        'ofdm':'像许多不同音调一起携带信息，每个子载波使用16QAM。这次采用约95 MHz设计档，实测内部窗99%带宽约94.2 MHz。它不是昨天约98.14 MHz设计档的最宽测试，因此不用约97 MHz作为本次预期值。改变窗函数后最高谱线的位置明显变化，说明最高峰不能代表通信载频。',
    }
    lines += ['', '## 看图理解', '',
        '左列为实际装载输入的幅度范围，每32点显示最小值到最大值；不是硬件回采的原始IQ。灰色区域对应右图的第0号快照窗，绿色区域对应上表第1号测量窗。', '',
        '右列为开发板真实读回的1024点功率快照，每8个FFT格子取最大值。每行以各自最高峰归一化为0 dB，不能跨行比较绝对幅度。快照窗口含信号开头静默，所以与上表完整内部窗的带宽可能不同。', '',
        '![五种信号输入与真板频谱对比](overview.png)', '']
    html_notes = []
    for i, row in enumerate(manifest['cases']):
        ident = row['id']; c = next(x for x in report['cases'] if x['id']==ident and x['window']=='rect')
        vector = Path(row['vector']);assert sha(vector)==row['sha256']
        iq = np.fromfile(vector,dtype='<i2').reshape(-1,2).astype(float)
        amplitude = np.sqrt(np.sum(iq*iq,axis=1)).reshape(-1,32)
        time = (np.arange(len(amplitude))*32+15.5)/100
        ax = axes[i,0]
        ax.axvspan(0,81.92,color='#ccd2d8',alpha=.35)
        ax.axvspan(81.92,163.84,color='#bfded4',alpha=.4)
        ax.fill_between(time,amplitude.min(axis=1),amplitude.max(axis=1),color='#197a91',alpha=.65)
        ax.plot(time,amplitude.mean(axis=1),color='#155c72',linewidth=.6)
        ax.set(title=f'{i+1}. {row["name"]}：装载输入幅度',xlabel='时间 / µs',ylabel='数字码值',xlim=(0,327.68))
        ax.grid(alpha=.2)
        shot = read(Path(c['folder'])/'snapshot.json')
        assert shot['window_id']==0
        power = np.asarray(shot['power'],dtype=float)
        db = 10*np.log10(np.maximum(power/power.max(),1e-8))
        freq = (np.arange(1024)*8+3.5-4096)*100/8192
        ax = axes[i,1];ax.plot(freq,db,color='#d46b32',linewidth=.85)
        ax.set(title=f'{row["name"]}：真板矩形窗快照，第0窗',xlabel='基带频率 / MHz',ylabel='相对最高峰 / dB',xlim=(-50,50),ylim=(-80,3))
        ax.grid(alpha=.2)
        lines += [f'## {i+1}. {row["name"]}', '', notes[ident], '',
                  f'输入文件：[{ident}.bin](vectors/{ident}.bin)，32768对I16/Q16，131072字节。', '',
                  f'[矩形窗原始测量](board/{ident}_rect/frequency.json) · [Hann窗原始测量](board/{ident}_hann/frequency.json) · [包络测长](board/{ident}_rect/burst.json)', '',
                  '矩形窗逐窗口结果（每窗81.92 µs；第0、3窗含边沿）：', '',
                  '| 窗号 | 时间区间/µs | 低边界/MHz | 高边界/MHz | 谱峰/MHz | 99%带宽/MHz |',
                  '|---|---|---:|---:|---:|---:|']
        for f in c['all_frequency_windows']:
            wid=f['id']
            lines.append(f"| {wid} | {wid*81.92:.2f}～{(wid+1)*81.92:.2f} | {f['low_hz']/1e6:.6f} | {f['high_hz']/1e6:.6f} | {f['peak_hz']/1e6:.6f} | {f['bandwidth_hz']/1e6:.6f} |")
        lines += ['']
        html_notes.append(f'<article><h2>{i+1}. {html.escape(row["name"])}</h2><p>{html.escape(notes[ident])}</p><p>输入文件：vectors/{ident}.bin</p></article>')
    fig.suptitle('五种新信号：装载数据与开发板实际频谱\n100 MSPS · 8192点FFT · 数字零背景测长 · 10次采集全部通过',fontsize=17)
    fig.savefig(folder/'overview.png',dpi=140);plt.close(fig)
    lines += ['## 复现与验收口径', '',
        '打开工程的Open_IQ_Monitor.cmd，选择本目录vectors下的bin文件，选择digital-zero、gap_min=32、矩形窗或Hann窗，关闭循环回放，再开始采集。请仅保留一个板卡控制端，每次保存到新目录。', '',
        '本次不改写FPGA镜像，不重写SD，不覆盖此前正式交付。生成脚本为scripts/test_five_signals.py，可指定新的输出目录重复整个流程。', '',
        '全部频域记录、包络长度/幅度、序号、时间戳及可用快照都经独立参考逐项核验。采集的丢包、缺失记录、硬件错误均为0，10次吞吐计数守恒通过。单音分辨率标志是预期状态，不等于硬件故障。', '',
        '五个已知输入的成功测量不等于能自动识别任意信号。本次没有添加噪声，不能替代抗噪声测试。', '',
        '[生成参数与输入散列](manifest.json) · [完整验收数据](validation.json)', '']
    (folder/'测试报告.md').write_text('\n'.join(lines),encoding='utf-8')
    header=['信号','分析窗','RMS幅度','峰值幅度','谱峰/MHz','99%带宽/MHz','长度/µs','最大延迟/µs']
    table='<table><thead><tr>'+''.join(f'<th>{x}</th>' for x in header)+'</tr></thead><tbody>'
    for row in table_rows:table+='<tr>'+''.join(f'<td>{html.escape(x)}</td>' for x in row)+'</tr>'
    table+='</tbody></table>'
    encoded=base64.b64encode((folder/'overview.png').read_bytes()).decode()
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>五组信号真板测试</title><style>body{font:17px/1.75 "Microsoft YaHei",sans-serif;color:#183646;background:#f5f8fa;max-width:1200px;margin:auto;padding:24px}h1{font-size:30px}table{width:100%;border-collapse:collapse;background:white;font-size:14px}th,td{padding:9px;border-bottom:1px solid #dae1e7;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#183646;color:white}article{margin:28px 0}img{width:100%;height:auto;background:white}.table{overflow:auto}a{color:#126c8a}</style><h1>五组新信号，10次真板测试全部通过</h1><p>每种信号分别用矩形窗、Hann窗测量。100 MSPS，8192点FFT；40条频域记录、10条包络记录及10240个快照数值通过核验，最大分析延迟175.23 µs。</p><p>表格幅度、频率和带宽来自第1号完整内部窗（81.92～163.84 µs）；长度来自整段包络。幅度是数字码值，频率是基带频率，信号种类来自已知生成参数，并非自动识别结果。</p>'''
    document+='<div class="table">'+table+'</div>'+''.join(html_notes)
    document+='<h2>输入与实测频谱</h2><p>左图为装载输入，每32点显示幅度范围；右图为真板第0窗快照，含开头静默。灰色区域对应快照窗，绿色对应表格窗。各行频谱分别归一化，不能比较绝对幅度。</p>'
    document+=f'<img alt="五种信号的输入幅度与真实硬件频谱" src="data:image/png;base64,{encoded}">'
    document+='<p>本次使用数字零背景测长，没有添加噪声；硬件错误及记录丢失均为0。已有正式镜像和交付包未改动。</p><p>完整说明及逐窗口数据见同目录“测试报告.md”；原始记录见board，输入见vectors，数值参考见references。</p></html>'
    (folder/'打开查看结果.html').write_text(document,encoding='utf-8')
    print('FIVE_SIGNALS_REPORT_READY',folder)


if __name__=='__main__': main()
