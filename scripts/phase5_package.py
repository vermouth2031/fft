"""Verify and archive the qualified Phase 5 compatible image and its raw evidence."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from record_build_stage import ROOT, sha
from record_boot_stage import verify_boot
from package_release import check
from package_validated import check_board, supplementary_evidence
from phase5_summarize_final import verify_report


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate():
    check(); verify_boot()
    board = check_board()
    checkout=read(ROOT/'reports/phase5_source_checkout_validation.json')
    require(checkout['status']=='PASS', 'Current source checkout audit is missing')
    for name, digest in checkout['files'].items():
        require(sha(ROOT/name)==digest, 'Audited source changed: '+name)
    measurements_path = ROOT/'reports/phase5_final_measurements.json'
    measurements = verify_report(measurements_path)
    extra, boot = supplementary_evidence()
    require(boot, 'Current SD installation/reset has not passed')
    cold_path = ROOT/'reports/current_cold_boot_validation.json'
    cold = read(cold_path)
    require(cold['status']=='PASS' and cold['previous_board_validation_sha256']==sha(ROOT/'reports/current_board_validation.json'),
            'Current physical cold boot is required')
    require(cold['hardware_before']==board['hardware'] and cold['epoch_before']==0 and
            not cold['jtag_used'] and not cold['program_download_performed'], 'Cold boot identity/method mismatch')
    hw = read(ROOT/'reports/hardware_validation.json')
    require(hw['setup_slack_ns']>=.4 and hw['hold_slack_ns']>=0 and measurements['maximum_analysis_us']<=175.5,
            'Compatible candidate does not meet the frozen Phase 5 gates')
    gui_folder = ROOT/'captures/phase5/final/gui_redesign'
    gui = read(gui_folder/'gui_validation.json')
    require(gui['status']=='PASS' and len(gui['tests'])==18 and gui['hardware']==board['hardware'] and
            gui['cleanup']['status']=='PASS', 'Current GUI regression is incomplete')
    for name, digest in gui['source_sha256'].items():
        require(sha(ROOT/name)==digest, 'GUI source changed: '+name)
    for name, digest in gui['files_sha256'].items():
        require(sha(gui_folder/name)==digest, 'GUI evidence changed: '+name)
    board_rows = [row for row in gui['tests'] if 'capture' in row]
    require(len(board_rows)==4 and all(row['numerical_verification']['status']=='PASS' for row in board_rows),
            'Four exact GUI board captures are required')
    demo_path=gui_folder.parent/'demo/gui_validation.json'
    demo=read(demo_path)
    demo_rows=[row for row in demo['tests'] if row['name'] in ('digital','robust','tone','ofdm')]
    presets_path=ROOT/'data/phase4_demo/presets.json'
    presets=read(presets_path)
    require({row['name'] for row in demo_rows}=={'digital','robust','tone','ofdm'} and
            all(row['status']=='PASS' for row in demo['tests']), 'Incomplete demo preset coverage')
    require(demo['status']=='PASS' and demo['cleanup']['status']=='PASS' and len(demo_rows)==4 and
            demo['wrapper_sha256']==sha(ROOT/'scripts/phase4_demo.py') and
            presets['build_id']==board['hardware']['build_id'] and presets['qualification_status']=='qualified',
            'Current demonstration presets have not passed')
    for row in demo_rows:
        result=row['numerical_verification']
        require(result['status']=='PASS' and row['metadata']['build_id']==board['hardware']['build_id'],
                'Demo capture has another image or failed numerically')
        for name,digest in result['files'].items():
            require(sha(Path(result['folder'])/name)==digest,'Demo raw evidence changed')
    for row in presets['presets']:
        require(sha(ROOT/row['vector'])==row['sha256'],'Demo input changed')
        if row.get('reference'):require(sha(ROOT/row['reference'])==row['reference_sha256'],'Demo reference changed')
    noise = read(ROOT/'reports/phase5_noise_validation.json')
    require(noise['status']=='COMPLETE' and noise['self_test']['status']=='PASS', 'Noise study incomplete')
    for row in noise['cases']:
        path = Path(row['raw']).resolve()
        require(path.is_relative_to(ROOT) and sha(path)==row['sha256'], 'Noise raw evidence changed')
    for mode, artifact in [('sd_card','BOOT_sd.BIN'),('ethernet_sd_card','BOOT_udp.BIN')]:
        require(sha(ROOT/'release'/mode/'BOOT.BIN')==sha(ROOT/'artifacts'/artifact), 'Boot package is stale')
    report = dict(status='PASS', hardware=board['hardware'], physical_cold_boot_verified=True,
        matrix_cases=measurements['matrix_cases'], legacy_check_cases=measurements['legacy_check_cases'],
        basic_board_cases=len(board['cases']), gui_tests=18, demo_board_cases=4, sd_cases=16, cold_boot_cases=3,
        maximum_analysis_us=measurements['maximum_analysis_us'], maximum_publish_us=measurements['maximum_publish_us'],
        minimum_widest_internal_obw_hz=measurements['minimum_widest_internal_obw_hz'],
        measurements_sha256=sha(measurements_path), gui_report_sha256=sha(gui_folder/'gui_validation.json'),
        cold_report_sha256=sha(cold_path), demo_report_sha256=sha(demo_path), presets_sha256=sha(presets_path),
        source_sha256=sha(Path(__file__)),
        scope='One 100 MSPS Phase 5 timing image; separate rejected/experimental candidates are not combined into its scores')
    return report, extra


def package(archive, report, extra):
    require(archive.is_relative_to(ROOT/'release') and archive.suffix=='.zip' and not archive.exists(),
            'Choose a new .zip under release/')
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT), 'Commit current changes before packaging')
    require(read(ROOT/'reports/phase5_complete_validation.json')==report, 'Run --check for this final source first')
    selected = set()
    omit = {'frequency.json','frequency.csv','burst.json','burst.csv'}
    def add(path):
        path = Path(path).resolve()
        require(path.is_relative_to(ROOT) and path.is_file(), 'Nonlocal/missing delivery source: '+str(path))
        if '__pycache__' not in path.parts and path.name not in omit:
            selected.add(path)
    # Preserve committed documentation/history, clearly distinguished by START_HERE.
    for raw in subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).split(b'\0'):
        if raw:
            add(ROOT/raw.decode('utf-8'))
    for folder in ['artifacts','build/config','build/phase5','captures/phase5','build/maintenance',
                   'release/sd_card','release/ethernet_sd_card']:
        for path in (ROOT/folder).rglob('*'):
            if path.is_file():
                add(path)
    for stage in ['simulation','hardware']:
        record=read(ROOT/f'reports/{stage}_provenance.json')
        for name in set(record['inputs'])|set(record['evidence'])|set(record['artifacts']):
            add(ROOT/name)
    for path in extra:
        add(path)
    for deployment_path in [ROOT/'reports/current_deployment.json',
                            *sorted((ROOT/'reports').glob('phase5_recovery_deployment_*.json'))]:
        deployment=read(deployment_path)
        require(deployment['status']=='PASS' and deployment['hardware']==report['hardware'],
                'Deployment identity differs: '+str(deployment_path))
        log=Path(deployment['log'])
        require(sha(log)==deployment['log_sha256'], 'Deployment log changed: '+str(log))
        add(deployment_path);add(log)
    for name in read(ROOT/'reports/phase5_final_measurements.json')['evidence']:
        add(ROOT/name)
    # Numerical C-model DLLs are installation inputs, not required to view captures;
    # rebuilding needs the recorded AMD tool installation and fresh provenance.
    files={path.relative_to(ROOT).as_posix():dict(bytes=path.stat().st_size,sha256=sha(path)) for path in sorted(selected)}
    start=('''# 第五阶段 100 MSPS 兼容版交付

当前成绩及边界见 reports/第五阶段实施记录.md 和 reports/phase5_complete_validation.json。
本包是同一构建的完整仿真、实板矩阵、SD 和物理冷启动证据。旧阶段报告、演示稿及旧候选属于历史资料，不代替本轮验收；125 MSPS 单独候选不得与本镜像拼接成绩。

使用 release/ethernet_sd_card 中的 BOOT.BIN 启动网络交互，或选择 release/sd_card 的独立 SD 自动测试镜像。每次只使用一套启动文件。Open_IQ_Monitor.cmd 启动上位机。

解压后运行 `python scripts/verify_delivery.py .` 核验逐文件 SHA-256；该命令仅检查内容完整性。原始流位于 captures/phase5，参考位于 build/phase5。每条记录的 JSON/CSV 可从二进制重建，因此本包省略这些重复数组。

原报告保留生成时绝对路径。重新构建需安装对应 Vivado/Vitis，重新生成本目录的软件/BSP、参考和验收证据；本包不承诺移动目录后旧绝对路径仍可执行。

输入为板内预装载回放，帧长度指突发包络区间，FFT 使用 AMD IP。离线噪声研究不等于连续不重复噪声的实板验收。
''').encode('utf-8')
    files['START_HERE.md']=dict(bytes=len(start),sha256=hashlib.sha256(start).hexdigest())
    manifest=dict(schema='iq-phase5-delivery-v1',created_at=datetime.datetime.now().astimezone().isoformat(),
        hardware_version=report['hardware']['hardware_version_hex'],build_id=report['hardware']['build_id'],
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        physical_cold_boot_verified=True,files=files)
    print('PHASE5_ARCHIVE_WRITE_START',len(files),'files',flush=True)
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(selected):
            name=path.relative_to(ROOT).as_posix()
            require(sha(path)==files[name]['sha256'], 'Source changed during packaging: '+name)
            if files[name]['bytes']>=100000000:print('PHASE5_ARCHIVE_LARGE_FILE',name,flush=True)
            z.write(path,name)
        z.writestr('START_HERE.md',start)
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('PHASE5_ARCHIVE_VERIFY_START',flush=True)
    with zipfile.ZipFile(archive) as z:
        require(set(z.namelist())==set(files)|{'manifest.json'}, 'Unexpected archive entries')
        require(json.loads(z.read('manifest.json'))==manifest,'Archive manifest differs')
        for name, row in files.items():
            with z.open(name) as stream:
                require(hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256'], 'ZIP SHA mismatch: '+name)
        # Reading every entry to EOF above also checks its ZIP CRC; do not
        # decompress several gigabytes a second time solely for testzip().
    receipt=dict(status='PASS',archive=str(archive),bytes=archive.stat().st_size,sha256=sha(archive),
                 file_count=len(files)+1,crc_checked=True,all_archive_sha256_checked=True)
    archive.with_name(archive.stem+'_check.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check',action='store_true');action.add_argument('--out',type=Path)
    args=parser.parse_args();report,extra=validate()
    if args.check:
        (ROOT/'reports/phase5_complete_validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print('PHASE5_COMPLETE_ACCEPTANCE_PASS')
    else:
        package(args.out.resolve(),report,extra)
