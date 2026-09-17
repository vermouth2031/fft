"""Create a dated, evidence-backed delivery without rewriting the offline release."""
from pathlib import Path
import datetime,hashlib,json,shutil,zipfile
from package_release import check
ROOT=Path(__file__).resolve().parents[1]
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    check()
    required=['board_validation_sd.json','board_validation_network.json','board_validation_network_measurements.json',
              'board_snapshot_validation.json','board_validation_extended.json','host_regression_final.json']
    for name in required:
        d=json.loads((ROOT/'reports'/name).read_text(encoding='utf-8-sig'))
        assert d.get('status')=='PASS' or d.get('passed') is True,name
    out=ROOT/'release/validated_20260917';out.mkdir(exist_ok=True)
    files={}
    def add(source,relative=None):
        if not source.is_file() or '__pycache__' in source.parts:return
        relative=relative or source.relative_to(ROOT)
        target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        sha=digest(source);assert digest(target)==sha
        files[Path(relative).as_posix()]={'sha256':sha,'bytes':target.stat().st_size}
    for folder in ('rtl','constraints','scripts','tests','firmware','host','docs','vendor','data','artifacts','reports'):
        for p in (ROOT/folder).rglob('*'):add(p)
    for name in ('README.md','PROJECT_STATUS.md','requirements.txt','Open_IQ_Monitor.cmd','Run_Network_Tests.cmd'):add(ROOT/name)
    for folder in ('sd_card','ethernet_sd_card'):
        for p in (ROOT/'release'/folder).rglob('*'):add(p,Path('boot_packages')/folder/p.relative_to(ROOT/'release'/folder))
    roots=[ROOT/'captures/sd_board_20260917_202436',ROOT/'captures/network_20260917_211639',ROOT/'captures/extended_20260917']
    # Include all GUI capture folders referenced by screenshot/numerical evidence.
    for record in json.loads((ROOT/'reports/board_snapshot_validation.json').read_text())['files']:
        p=ROOT/record['file']
        if p.parent.parent==ROOT/'captures':roots.append(p.parent)
    for folder in set(roots):
        for p in folder.rglob('*'):
            if p.name not in ('frequency.json','burst.json','frequency.csv','burst.csv'):add(p)
    # The offline boot READMEs are historical; explain the verified state in this delivery.
    for folder in ('sd_card','ethernet_sd_card'):
        p=out/'boot_packages'/folder/'README.txt'
        p.write_text('Zybo Z7-20: '+('16-case SD automatic tests' if folder=='sd_card' else 'UDP network interactive capture')+'\nCopy BOOT.BIN to the FAT32 SD card root.\nActual board tests passed on 2026-09-17. See reports and manifest.json for the exact scope.\n',encoding='utf-8')
        files[p.relative_to(out).as_posix()]={'sha256':digest(p),'bytes':p.stat().st_size}
    readme=out/'START_HERE.md'
    readme.write_text('# 已实板验证交付包\n\n先阅读 `reports/最终验收与交付说明.md` 和 `docs/演示操作卡.md`。\n\n当前硬件基准：100 MSPS 内部数字 IQ 回放、8192 点 AMD FFT。源码、启动包、原始二进制证据和报告均在包内。旧离线报告保留原始日期和状态，不能用其历史“未板测”字段覆盖后续实测结果。\n\n图形程序：`python host/monitor.py`；自动脚本中的网卡 GUID 和本机 Python 路径针对原电脑，换电脑请使用文档中的通用 Python 命令。\n\n为避免重复存储，部分大体积 CSV/JSON 数组未放入包内；可以使用 `python host/iq_client.py decode --freq 路径/frequency.bin --burst 路径/burst.bin --out 导出目录` 重新导出。原始 provenance 请同时查看同目录 capture.json。\n\n断网轮次故意失败，用于验证失效检测。正常验收与故障注入分别记录。\n',encoding='utf-8')
    files['START_HERE.md']={'sha256':digest(readme),'bytes':readme.stat().st_size}
    manifest={'created_at':datetime.datetime.now().astimezone().isoformat(),'board':'Zybo Z7-20 / XC7Z020',
              'board_tested':True,'status':'BASELINE_VALIDATED','input':'Internal I16/Q16 replay at nominal 100 MSPS',
              'scope':['RTL integer oracle','post-route STA','SD 64 cases','UDP 10s and 60s','6103.516 bursts/s pressure',
                       'loss detection','Windows adapter outage recovery','GUI','UART','JTAG','84 display snapshots'],
              'not_implemented':['125 MSPS extension','external ADC','custom FFT'],
              'metrology_calibrated':False,'files':files}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(files):z.write(out/name,name)
        z.write(out/'manifest.json','manifest.json')
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    report={'status':'PASS','directory':str(out),'archive':str(archive),'archive_bytes':archive.stat().st_size,
            'archive_sha256':digest(archive),'file_count':len(files)+1,'zip_crc_check':'PASS','file_hash_readback':'PASS'}
    (ROOT/'release/validated_20260917_package_check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
