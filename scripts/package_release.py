"""Gate, assemble and hash local deliverables. Never writes a physical SD card."""
from pathlib import Path
import argparse,hashlib,json,shutil,zipfile,datetime,stat
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check():
    hw=json.loads((ROOT/'reports/hardware_validation.json').read_text())
    sw=json.loads((ROOT/'reports/software_validation.json').read_text())
    core=json.loads((ROOT/'reports/core_validation.json').read_text())
    assert hw['status']=='PASS' and hw['setup_slack_ns']>=0 and hw['hold_slack_ns']>=0,'Hardware timing failed'
    assert hw['cdc_critical']==0 and hw['unconstrained_internal_endpoints']==0
    assert core['status']=='PASS' and core['frequency_records']==64 and core['exact_fft_points']==524288
    assert sw['status']=='BUILD_PASS' and sw['xsa_sha256']==sha(ROOT/'artifacts/iq_analyzer.xsa'),'Software targets another XSA'
    for name,digest in sw['artifacts'].items():assert sha(ROOT/'artifacts'/name)==digest,('ELF changed',name)
    for name,digest in sw['firmware_sources'].items():assert sha(ROOT/'firmware'/name)==digest,('Firmware changed',name)
    rtl_time=max(p.stat().st_mtime for p in (ROOT/'rtl').glob('*.sv'))
    assert (ROOT/'reports/core_validation.json').stat().st_mtime>rtl_time,'Core numerical report predates RTL'
    assert (ROOT/'artifacts/iq_analyzer.bit').stat().st_mtime>rtl_time,'RTL newer than implemented bitstream'
    assert sha(ROOT/'artifacts/iq_analyzer.bit')==sha(ROOT/'build/board/iq_board.runs/impl_1/system_wrapper.bit')
    for script,marker in [('sim_core','CORE_PASS'),('sim_axi','AXI_PASS'),('sim_units','UNITS_PASS'),
                           ('sim_builder','BUILDER_PASS'),('sim_measurements','MEASUREMENTS_PASS')]:
        logs=sorted(ROOT.glob(script+'*.log'),key=lambda p:p.stat().st_mtime,reverse=True)
        passing=[p for p in logs if marker in p.read_text(errors='replace') and 'Fatal:' not in p.read_text(errors='replace')]
        assert passing,('Missing successful regression',script)
        if script in ('sim_core','sim_axi','sim_measurements'):assert passing[0].stat().st_mtime>rtl_time,('Stale regression',script)
    return hw,sw,core

def package():
    hw,sw,core=check();release=ROOT/'release';release.mkdir(exist_ok=True)
    sd=release/'sd_card';sd.mkdir(exist_ok=True);(sd/'VECTORS').mkdir(exist_ok=True)
    net=release/'ethernet_sd_card';net.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'artifacts/BOOT_sd.BIN',sd/'BOOT.BIN')
    shutil.copyfile(ROOT/'artifacts/BOOT_udp.BIN',net/'BOOT.BIN')
    names=dict(zero='ZERO',tone_pos_fs4='POS25',tone_neg_fs4='NEG25',burst_fs4='BURST',
      qpsk_sps4='QPSK4',qpsk_sps2='QPSK2',short512_boundary='SHORT512',negative_fullscale_dc='FULLNEG')
    golden=json.loads((ROOT/'data/golden_results.json').read_text())['cases']
    assert [c['name'] for c in golden[:8]]==list(names),'SD fixture order and reference order differ'
    for long,short in names.items():shutil.copyfile(ROOT/'data/vectors'/(long+'.bin'),sd/'VECTORS'/(short+'.BIN'))
    manifest=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),board='Zybo Z7-20 / xc7z020clg400-1',
      hardware=hw,software=sw,simulation=core,board_tested=False,
      artifacts={name:sha(ROOT/'artifacts'/name) for name in ('iq_analyzer.bit','iq_analyzer.xsa','iq_udp.elf','iq_sd.elf',
        'zynq_fsbl.elf','ps7_init.tcl','BOOT.BIN','BOOT_sd.BIN','BOOT_udp.BIN')},
      source={p.relative_to(ROOT).as_posix():sha(p) for folder in ('rtl','constraints','scripts','firmware','tests','host','vendor/boards')
              for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts})
    (release/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copyfile(ROOT/'reports/离线验证报告.md',release/'离线验证报告.md')
    evidence=release/'evidence';evidence.mkdir(exist_ok=True)
    for name in ('hardware_validation.json','software_validation.json','core_validation.json',
                 'timing_summary.rpt','utilization_flat.rpt','cdc.rpt','drc.rpt','bus_skew.rpt','methodology.rpt'):
        shutil.copyfile(ROOT/'reports'/name,evidence/name)
    shutil.copyfile(ROOT/'build/vivado/iq_analyzer.sim/sim_1/behav/xsim/core_results.txt',evidence/'rtl_core_results.txt')
    for dest,mode in [(sd,'SD 自动运行 16 个有限采集测试并保存结果'),(net,'以太网交互与连续采集')]:
        (dest/'README.txt').write_text(f'Zybo Z7-20 / {mode}\n将本目录内容复制到已有 FAT32 分区根目录。\n不需要烧写磁盘镜像，也不要同时复制两套 BOOT.BIN。\n实际板测尚未执行；操作详见工程 docs/使用与设计说明.md。\n',encoding='utf-8')
        # Some vendor license files carry a Windows read-only attribute.
        # Keep their text intact, but permit rebuilding our generated copies.
        for p in (dest/'LICENSES').glob('*'):
            if p.is_file():p.chmod(stat.S_IREAD|stat.S_IWRITE)
        shutil.copytree(ROOT/'vendor/licenses',dest/'LICENSES',dirs_exist_ok=True,copy_function=shutil.copyfile)
        with zipfile.ZipFile(release/(dest.name+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for p in dest.rglob('*'):
                if p.is_file():z.write(p,p.relative_to(dest))
    with zipfile.ZipFile(release/'iq_analyzer_source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for folder in ('rtl','constraints','scripts','tests','firmware','host','docs','vendor','data'):
            for p in (ROOT/folder).rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts:z.write(p,p.relative_to(ROOT))
        for name in ('README.md','PROJECT_STATUS.md','requirements.txt'):
            z.write(ROOT/name,name)
    print('PACKAGE_PASS',release)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.check:check();print('PACKAGE_CHECK_PASS')
    else:package()
