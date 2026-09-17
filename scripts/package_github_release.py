"""Build public GitHub assets without machine setup records or tool caches."""
from pathlib import Path
import hashlib,json,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
    version=json.loads((ROOT/'VERSION.json').read_text());tag=version['git_tag']
    out=ROOT/'release/github'/tag;out.mkdir(parents=True,exist_ok=True)
    assets=[]
    def archive(name,paths,readme):
        target=out/name;manifest={}
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(set(paths)):
                if not p.is_file():continue
                rel=p.relative_to(ROOT).as_posix();z.write(p,rel);manifest[rel]={'bytes':p.stat().st_size,'sha256':sha(p)}
            z.writestr('ASSET_README.md',readme)
            z.writestr('ASSET_MANIFEST.json',json.dumps({'version':version,'files':manifest},ensure_ascii=False,indent=2))
        with zipfile.ZipFile(target) as z:assert z.testzip() is None
        assets.append({'file':name,'bytes':target.stat().st_size,'sha256':sha(target),'files':len(manifest)})
    hardware=list((ROOT/'artifacts').glob('*'))+list((ROOT/'vendor/licenses').glob('*'))+list((ROOT/'vendor/boards').rglob('*.xml'))
    for mode in ('sd_card','ethernet_sd_card'):
        hardware.extend(p for p in (ROOT/'release'/mode).rglob('*') if p.name!='README.txt')
    archive(f'fft-{tag}-hardware.zip',hardware,
            '# 硬件与启动包\n\n解压到 Git 源码根目录。SD 自动测试使用 release/sd_card/ 的内容；网络交互使用 release/ethernet_sd_card/BOOT.BIN。只选择一个 BOOT.BIN 放入 FAT32 卡根目录。\n\n硬件及固件已于 2026-09-17 完成实板测试。使用条件和第三方声明见源码 THIRD_PARTY_NOTICES.md。\n')
    evidence=[]
    sd=ROOT/'captures/sd_board_20260917_202436'
    evidence.extend((sd/'raw').rglob('*'))
    for p in (sd/'decoded').rglob('board_validation.json'):evidence.append(p)
    allowed={'.bin','.json','.py','.tcl','.txt'}
    excluded={'frequency.json','burst.json','network_link.json','ready.txt','trigger.txt'}
    for base in (ROOT/'captures/network_20260917_211639',ROOT/'captures/extended_20260917'):
        for p in base.rglob('*'):
            if p.suffix.lower() in allowed and p.name not in excluded:evidence.append(p)
    for record in json.loads((ROOT/'reports/board_snapshot_validation.json').read_text())['files']:
        p=ROOT/record['file']
        if p.parent.parent==ROOT/'captures':
            evidence.extend(x for x in p.parent.iterdir() if x.suffix.lower() in ('.bin','.json') and x.name not in excluded)
    evidence.extend([ROOT/'captures/extended_20260917/gui/final_layout.png',ROOT/'captures/extended_20260917/uart_startup.log'])
    # Include only the reports already reviewed for Git publication.
    tracked=subprocess.check_output(['git','ls-files','-z','reports'],cwd=ROOT).decode().split('\0')
    evidence.extend(ROOT/p for p in tracked if p)
    archive(f'fft-{tag}-board-evidence.zip',evidence,
            '# 实板证据\n\n解压到 Git 源码根目录。二进制记录和元数据均保留，较大的 CSV/JSON 数组可用 host/iq_client.py decode 重新生成。故障注入轮次预期报告不完整，不能与正常验收统计混用。\n\n部分文档记录本机原路径；原始验证日期与版本标识不是同一个日期。设备准备、磁盘与网卡身份记录不包含在附件中。\n')
    (out/'SHA256SUMS.txt').write_text(''.join(f"{a['sha256']}  {a['file']}\n" for a in assets),encoding='ascii')
    (out/'assets.json').write_text(json.dumps(assets,indent=2)+'\n')
    print(json.dumps(assets,indent=2))
if __name__=='__main__':main()
