from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, zipfile, gzip
from datetime import datetime, timezone

ROOT=Path('D:/fft')
SRC=ROOT/'fft_phase13_reproduction_20261013'
REPO=ROOT/'phase13_github_archive_20261019'
DEST=REPO/'archives/phase13-report-reproduction-20261019'
ASSETS=ROOT/'phase13_archive_assets_20261019'
TAG='v2026.10.19-phase13-report-reproduction'
BASE='0f224112cf0480e7e4eefcb2077350f2634b4135'
DEST.mkdir(parents=True,exist_ok=True)
ASSETS.mkdir(parents=True,exist_ok=True)
entries=[]; omitted=[]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()
def record(p, location, digest=None):
    entries.append({'source':str(p),'archived_as':location,'bytes':p.stat().st_size,'sha256':digest or sha(p)})
def copy(p,rel):
    out=DEST/rel; out.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(p,out)
    assert sha(p)==sha(out)
    record(p,'git:'+out.relative_to(REPO).as_posix())
    return out
def files(root,skip_dirs=(),skip_suffixes=()):
    for folder,dirs,names in os.walk(root):
        for d in list(dirs):
            if d in set(skip_dirs)|{'.git','__pycache__','.Xil','xsim.dir'}:
                dirs.remove(d); omitted.append(str(Path(folder)/d))
        for n in sorted(names):
            p=Path(folder)/n
            if p.suffix.lower() in skip_suffixes or n.startswith('~$'):
                omitted.append(str(p));continue
            if p.suffix.lower() in {'.pem','.key','.pfx','.p12'} or n=='.env':
                raise RuntimeError('Unexpected credential file: '+str(p))
            yield p
secret=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
text_suffixes={'.py','.tcl','.json','.md','.txt','.log','.csv','.yml','.yaml','.cmd','.ps1','.xml','.ini'}
def scan(p):
    if p.suffix.lower() in text_suffixes:
        with p.open('rb') as f:
            tail=b''
            for b in iter(lambda:f.read(1024*1024),b''):
                if secret.search(tail+b):raise RuntimeError('Possible credential in '+str(p))
                tail=b[-256:]
def pack(name, groups):
    out=ASSETS/name; count=0
    print('Packing',name,flush=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for prefix,root,items in groups:
            for p in items:
                scan(p)
                dest=prefix+'/'+p.relative_to(root).as_posix()
                before=p.stat();h=hashlib.sha256()
                with p.open('rb') as source,z.open(dest,'w',force_zip64=True) as target:
                    for b in iter(lambda:source.read(1024*1024),b''):
                        h.update(b);target.write(b)
                after=p.stat()
                assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),str(p)
                record(p,name+':'+dest,h.hexdigest());count+=1
                if count%5000==0:print(' files',count,flush=True)
    print('Packed',name,count,out.stat().st_size,flush=True)
    return out

for name in ['报告.docx','报告.pdf']:
    out=copy(ROOT/name,'report/'+name)
    shutil.copy2(out,ASSETS/('final_report'+out.suffix))
with zipfile.ZipFile(ROOT/'报告.docx') as z: assert z.testzip() is None
assert (ROOT/'报告.pdf').read_bytes()[:5]==b'%PDF-'
copy(ROOT/'Phase13项目完整交接文档_20261013.md','context/Phase13项目完整交接文档_20261013.md')
for n in ['result.json','STATUS.txt','复现结果.txt','test_context.json','physical_cycle_confirmation.json','portable_package_validation.json','bitstream_byte_comparison.json']:
    copy(SRC/'reproduction'/n,'reproduction-summary/'+n)
for folder,target in [('报告三图片','figures/chapter3-original'),('报告四图片','figures/chapter4-original')]:
    for p in (ROOT/folder).iterdir():
        if p.is_file():copy(p,target+'/'+p.name)
for n in ['figure4_7.png','figure4_9.png','screenshot_evidence.json','capture_same_window.py']:
    copy(ROOT/'report8_edit_20261014'/n,'figures/chapter4-corrected/'+n)

gitstatus=subprocess.check_output(['git','status','--porcelain=v1','-z'],cwd=SRC)
status=[]
for line in gitstatus.split(b'\0'):
    if line:status.append({'status':line[:2].decode(),'path':line[3:].decode('utf-8')})
diff=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=SRC)
(DEST/'reproduction-worktree.patch').write_bytes(diff)
(DEST/'reproduction-worktree-status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
assert not subprocess.check_output(['git','diff','--name-only','--','rtl','host','firmware','scripts','config','constraints','tests'],cwd=SRC).strip()

pack('phase13_reproduction_snapshot.zip',[
    ('reports',SRC/'reports',files(SRC/'reports')),
    ('reproduction',SRC/'reproduction',files(SRC/'reproduction',skip_dirs=('portable_verification','inherited_release'))),
    ('release/phase13_sd_verified',SRC/'release/phase13_sd_verified',files(SRC/'release/phase13_sd_verified')),
    ('launchers',SRC,[SRC/'Open_Reproduced_IQ_Monitor.cmd']),
])
pack('phase13_simulation_capture.zip',[
    ('report3_capture_20261014',ROOT/'report3_capture_20261014',files(ROOT/'report3_capture_20261014')),
    ('报告三图片',ROOT/'报告三图片',files(ROOT/'报告三图片')),
])
pack('phase13_board_capture.zip',[
    ('report4_capture_20261014',ROOT/'report4_capture_20261014',files(ROOT/'report4_capture_20261014',skip_suffixes=('.docx',))),
    ('报告四图片',ROOT/'报告四图片',files(ROOT/'报告四图片')),
    ('corrected_same_window',ROOT/'report8_edit_20261014',[ROOT/'report8_edit_20261014'/n for n in ['figure4_7.png','figure4_9.png','screenshot_evidence.json','capture_same_window.py']]),
])
manifest={'archive_date':'2026-10-19','created_at':datetime.now(timezone.utc).isoformat(),'repository':'https://github.com/vermouth2031/fft','branch':'archive/phase13-report-reproduction-20261019','tag':TAG,'base_commit':BASE,'reproduction_source_commit':'cb04c3bb36940ad93665691d92cb46f533961107','implementation_changed':False,'report_selection':'User explicitly confirmed D:/fft/报告.docx and D:/fft/报告.pdf. Copied without edits; no claim of a new content or layout review.','test_dates':'2026-10-13 reproduction; 2026-10-14 report captures. Archive only; no new board test on archive date.','omitted':omitted,'files':entries}
(DEST/'file-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(DEST/'file-manifest.json',ASSETS/'file-manifest.json')
assets=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(ASSETS.iterdir()) if p.is_file() and p.name not in ['SHA256SUMS.txt','asset-manifest.json']]
(DEST/'asset-manifest.json').write_text(json.dumps(assets,indent=2),encoding='utf-8')
sums=''.join(a['sha256']+'  '+a['name']+'\n' for a in assets)
(ASSETS/'SHA256SUMS.txt').write_text(sums,encoding='utf-8')
(DEST/'SHA256SUMS.txt').write_text(sums,encoding='utf-8')
readme='''# Phase13 最终报告与后续复现材料归档

归档日期：2026-10-19。最终报告由用户明确确认为 `D:/fft/报告.docx` 与 `D:/fft/报告.pdf`，两份文件按原字节归档，没有修改内容、目录、字体或排版，也没有重新导出 PDF。

## 获取文件

- [最终 Word 报告](report/报告.docx)
- [最终 PDF 报告](report/报告.pdf)
- [完整归档附件](https://github.com/vermouth2031/fft/releases/tag/v2026.10.19-phase13-report-reproduction)
- [逐文件来源、大小和 SHA-256](file-manifest.json)
- [下载附件 SHA-256](SHA256SUMS.txt)

| 附件 | 内容 |
| --- | --- |
| final_report.docx / final_report.pdf | 用户确认的最终报告原文件 |
| phase13_reproduction_snapshot.zip | 本地 reports 完整快照、复现操作记录、失败尝试与最终成功验收、已封装的 SD 发布包、GUI 启动脚本 |
| phase13_simulation_capture.zip | 第三章仿真截图、WDB/VCD、波形配置、脚本、日志、原始数据和证据索引 |
| phase13_board_capture.zip | 第四章实板采集、有限回放、DMA1000、连续300秒、截图与修正后的同窗口图 |
| file-manifest.json / SHA256SUMS.txt | 文件溯源与下载校验 |

## 工程和数据的对应关系

本归档分支以 `0f224112cf0480e7e4eefcb2077350f2634b4135` 为基础；后续复现使用的源提交为 `cb04c3bb36940ad93665691d92cb46f533961107`。实现提交为 `806af4d4d50d696c358c5f22563000a9d56f899e`。本次未修改 RTL、PS 固件或上位机实现。原发布标签 `v2026.10.13-phase13-structure160-usb-sd-validated` 保持不变。

工程配置：I/Q 各16 bit、160 MSPS、16384点 FFT，构建 ID `4757a33c02eed50a403db87d09cb091f`。复现记录保留于 [reproduction-summary](reproduction-summary)：2026-10-13 的 RAM/JTAG 有限79例、宽带272例、DMA1000及故障用例、连续60/300秒与 SD 真正断电冷启动验收；2026-10-14 的报告采集存于截图包。2026-10-19 是归档日期，不代表重新执行了上述测试。

`reports` 快照还包含前序阶段的历史证据，不能将其全部理解为本次新增测试。初次 epoch=79 的冷启动检查和失败的 GUI/Python 尝试作为历史记录保留，最终通过的冷启动以 epoch=0 开始的验收为准。

## 截图使用说明

`figures/chapter3-original` 和 `figures/chapter4-original` 保留原截图、原索引及原文件名，截图文件名不一定等于最终报告的题注编号。

最终报告图4-7和图4-9对应的修正图分别为 [figure4_7.png](figures/chapter4-corrected/figure4_7.png) 与 [figure4_9.png](figures/chapter4-corrected/figure4_9.png)。[同窗口证据](figures/chapter4-corrected/screenshot_evidence.json) 明确记录频域数值与谱快照均对应窗口0。原始截图仅用于追溯，不应覆盖修正图。突发长度来自独立突发记录，不能等同于 FFT 窗口长度。

第三章证据索引保留不同单元测试的实际时钟、核心 WDB 冻结范围与完整验证来源；不得把所有单元波形都解释为160 MHz或完整核心回归。前端离线查看截图来源于已采集的真板记录，不代表归档当日实时连接。

## 恢复与核验

检出本归档标签后，将 `phase13_reproduction_snapshot.zip` 解压到一个独立的工程副本，恢复其中的 reports、reproduction、release 和启动脚本。ZIP 内 `launchers/Open_Reproduced_IQ_Monitor.cmd` 对应原工程根目录的启动脚本；其中绝对路径可能需要根据新机器调整。此操作会用后续复现数据覆盖该副本原有 reports，因此请先保留原发布版本。`reproduction-worktree.patch` 和 `reproduction-worktree-status.json` 记录原复现工作区相对于源提交的修改与删除。

已验证的 SD 分发包位于快照中的 `release/phase13_sd_verified`，其中有独立的 `SHA256SUMS.txt`、源代码包、启动包与冷启动证据包。它与2026-10-13第一次发布的构建产物有独立散列，应按各自清单核验，不能混用。

下载后先根据 `SHA256SUMS.txt` 核验附件，再根据 `file-manifest.json` 对照 ZIP 内逐文件 SHA-256。清单保留原本机路径作为溯源信息，恢复时按归档相对路径使用。

未重复收入 portable_verification 解压副本及 inherited_release 副本；已有封装验证包与原发布标签可恢复相应内容。仿真缓存（.Xil、xsim.dir、__pycache__）及第四章工作区中旧报告副本未收入，具体排除路径见清单。本归档没有更新 main，也没有改变原工程分支或原发布附件。
'''
(DEST/'README.md').write_text(readme,encoding='utf-8')
print('DONE',len(entries),'source files;',json.dumps(assets),flush=True)

# Keep the repository manifest compact; Release keeps the original JSON.
p=DEST/'file-manifest.json'
(DEST/'file-manifest.json.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0))
p.unlink()
