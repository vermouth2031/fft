"""Create a new complete Phase 4 delivery; never overwrite an existing release."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from record_build_stage import ROOT,sha,verify as verify_stage
from record_boot_stage import verify_boot
from package_release import check
from package_validated import check_board,supplementary_evidence
from phase4_summarize_final import verify_report
from phase4_check_links import audit as audit_links

def require(ok,message):
    if not ok:raise ValueError(message)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'release/phase4-complete-20260922')
    args=parser.parse_args();out=args.out.resolve()
    require(out.is_relative_to(ROOT/'release') and not out.exists() and not out.with_suffix('.zip').exists(),'Use a new release directory')
    check();verify_boot();board=check_board();extra,boot=supplementary_evidence()
    measured=verify_report(ROOT/'reports/phase4_final_measurements.json')
    complete=read(ROOT/'reports/phase4_complete_validation.json')
    require(complete['status']=='PASS' and boot and complete['physical_cold_boot_verified'],'Final SD/cold acceptance missing')
    require(complete['hardware']==board['hardware'] and complete['measurements_sha256']==sha(ROOT/'reports/phase4_final_measurements.json'),
            'Completion report belongs to another build')
    for name,digest in complete['evidence'].items():require(sha(ROOT/name)==digest,'Completion evidence changed: '+name)
    for name,digest in complete['artifacts'].items():require(sha(ROOT/'artifacts'/name)==digest,'Final artifact changed')
    ppt=ROOT/'reports/答辩材料/数字IQ分析器_答辩稿.pptx'
    visual=read(ROOT/'reports/答辩材料/视觉检查.json')
    require(ppt.is_file() and visual['status']=='PASS' and visual['pptx_sha256']==sha(ppt),'Presentation visual acceptance missing')
    receipt=read(ROOT/'build/phase4_deck/final_validation.json')
    require(receipt['finalSha256']==sha(ppt) and receipt['firstPartyImport']['passed'] and
            receipt['packageIntegrity']['findingCount']==0 and receipt['presentationLayout']['findingCount']==0 and
            receipt['nativeChartValidation']['passed'],'Presentation finalizer receipt is not valid for this deck')
    checkout=read(ROOT/'reports/phase4_source_checkout_validation.json')
    require(checkout['status']=='PASS','Source checkout validation missing')
    import hashlib
    for name,digest in checkout['files'].items():
        require(sha(ROOT/name)==digest,'Checked source changed: '+name)
        blob=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)
        require(hashlib.sha256(blob).hexdigest()==digest,'Commit differs from checked source: '+name)
    require(audit_links(ROOT)['status']=='PASS','Current documentation contains broken or non-portable links')
    old_zip=ROOT/'release/phase3-complete-20260922.zip'
    require(sha(old_zip)=='1c2dc16ff59d063ae871dcf3c9f03617661b33c34d306a3e6a08da0f6deeb84c','Frozen Phase 3 release changed')
    out.mkdir(parents=True)
    files={}
    def add(source,relative=None):
        source=Path(source).resolve()
        require(source.is_relative_to(ROOT) and source.is_file(),'Invalid delivery source: '+str(source))
        if '__pycache__' in source.parts:return
        name=Path(relative) if relative else source.relative_to(ROOT)
        destination=(out/name).resolve();require(destination.is_relative_to(out),'Unsafe archive path')
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        digest=sha(source);require(sha(destination)==digest,'Copy differs: '+str(name))
        files[name.as_posix()]=dict(bytes=source.stat().st_size,sha256=digest)
    def tree(folder):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.name not in ('frequency.json','frequency.csv','burst.json','burst.csv'):
                add(p)
    for folder in ('rtl','constraints','firmware','host','tests','scripts','docs','vendor','data','config','.github'):
        tree(folder)
    for name in ('README.md','CHANGELOG.md','VERSION.json','THIRD_PARTY_NOTICES.md','requirements.txt',
                 'Open_IQ_Monitor.cmd','Run_Network_Tests.cmd','.gitattributes','.gitignore',
                 '第二阶段优化实施方案.md','第三阶段优化实施方案.md','第四阶段优化实施方案.md'):
        add(ROOT/name)
    for p in (ROOT/'artifacts').iterdir():
        if p.is_file():add(p)
    for mode in ('ethernet_sd_card','sd_card'):
        for p in (ROOT/'release'/mode).rglob('*'):
            if p.is_file():add(p,Path('boot_packages')/mode/p.relative_to(ROOT/'release'/mode))
    for stage in ('simulation','hardware'):
        verify_stage(stage);provenance=read(ROOT/'reports'/f'{stage}_provenance.json')
        for name in set(provenance['inputs'])|set(provenance['evidence']):add(ROOT/name)
    for path in extra:add(path)
    for name in measured['evidence']:add(ROOT/name)
    for name in complete['evidence']:add(ROOT/name)
    for name in ('phase4_final_measurements.json','phase4_complete_validation.json','phase4_requirements.json',
                 'phase4_candidate_decisions.json','phase4_candidate_import.json','phase4_source_checkout_validation.json',
                 '最终电路设计说明.md','第四阶段完整验收报告.md','第四阶段时钟可行性结论.md',
                 '帧长度定义与误差分析.md','frame_length_validation.json','冷启动验证报告.md',
                 'hardware_validation.json','software_validation.json','core_validation.json','boot_provenance.json',
                 'utilization_flat.rpt','timing_summary.rpt','worst_paths.rpt','cdc.rpt','drc.rpt','bus_skew.rpt',
                 'phase2_latency_validation.json','qualification_tool_validation.json','构建验证报告.md'):
        add(ROOT/'reports'/name)
    tree('reports/答辩材料')
    for folder in ('build/phase4_candidate_evidence_20260922','build/phase4_clock_matrix_20260922_v4',
                   'build/phase4_initial_freeze_20260922','build/phase4_frequency_20260922_v2','build/phase4_noise_20260922'):
        tree(folder)
    for name in ('generated_clocks.tcl','build_identity.json'):add(ROOT/'build/config'/name)
    for p in (ROOT/'build/phase4_deck').iterdir():
        if p.is_file() and (p.suffix=='.png' or p.name in ('authoring.json','final_validation.json')):add(p)
    # These are historical summaries, not live-bound acceptance for the new ID.
    for name in ('phase4_existing_hardware_validation.json','phase4_widest_validation.json','phase4_baseline.json'):
        add(ROOT/'reports'/name,Path('historical')/name)
    start=out/'START_HERE.md'
    start.write_text('''# 第四阶段完整交付

先阅读 [README](README.md)、[完整验收报告](reports/第四阶段完整验收报告.md) 和 [电路说明](reports/最终电路设计说明.md)。

本包为接口 0x00010002 的 100 MSPS 八路扫描组合版本，包含完整仿真、当前真板矩阵、SD 读回与此次物理冷启动证据。输入是预装载后的板内回放，FFT 使用 AMD IP。

`boot_packages/ethernet_sd_card` 是网络交互镜像；`boot_packages/sd_card` 是自动 SD 测试镜像，每次只选择一套。运行 `python scripts/phase4_demo.py` 可打开四个冻结演示预设。

在解压目录执行 `python scripts/verify_delivery.py .` 核验全部文件散列。这是内容完整性检查，不是重新运行 Vivado 或板卡测试。重建时需要安装对应工具并重新建立实板证据。

历史 JSON 保留采集时的绝对路径；当前原始数据与参考在包内 `captures/phase4_final_20260922` 和 `build/phase4_final_20260922`。离线 GUI 可打开其中单个采集目录。原始流可重新导出逐条 JSON/CSV，包内省略这些重复数组。

`historical` 和初轮源码归档记录旧四路测量范围；归档内的旧本机路径不是当前运行入口。独立候选的源码、时序和基础板测位于 `build/phase4_candidate_evidence_20260922`。初轮全部旧回放原始目录保留在原工作区；本包当前同一构建已重新测量相同冻结用例。

第三阶段完整 ZIP 单独保留，不作为当前冷启动证据。125 MSPS 实验未晋升；实拍板卡照片和现场视频尚未提供，现有 GUI 截图来自真实采集。
''',encoding='utf-8')
    files['START_HERE.md']=dict(bytes=start.stat().st_size,sha256=sha(start))
    links=audit_links(out)
    require(links['status']=='PASS','Packaged documentation link check failed: '+str(links['errors']))
    link_report=out/'documentation_links.json'
    link_report.write_text(json.dumps(links,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files['documentation_links.json']=dict(bytes=link_report.stat().st_size,sha256=sha(link_report))
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    manifest=dict(schema='iq-phase4-delivery-v1',created_at=datetime.datetime.now().astimezone().isoformat(),
        hardware_version=board['hardware']['hardware_version_hex'],build_id=board['hardware']['build_id'],
        source_commit=commit,board_tested=True,physical_cold_boot_verified=True,
        phase4_matrix_cases=measured['matrix_cases'],phase4_legacy_checks=measured['legacy_check_cases'],
        historical_baseline_archive_sha256=sha(old_zip),files=files)
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    subprocess.run([sys.executable,'scripts/verify_delivery.py',str(out)],cwd=ROOT,check=True)
    archive=out.parent/(out.name+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(files):z.write(out/name,name)
        z.write(out/'manifest.json','manifest.json')
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None,'ZIP CRC failed')
        require(set(z.namelist())==set(files)|{'manifest.json'},'Unexpected archive entries')
        import hashlib
        for name,record in files.items():
            with z.open(name) as stream:require(hashlib.file_digest(stream,'sha256').hexdigest()==record['sha256'],'Archive SHA mismatch: '+name)
    result=dict(status='PASS',directory=str(out),archive=str(archive),bytes=archive.stat().st_size,
        sha256=sha(archive),file_count=len(files)+1,crc_checked=True,all_archive_sha256_checked=True)
    (out.parent/(out.name+'_check.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
