"""Gate, assemble and hash local deliverables. Never writes a physical SD card."""
from pathlib import Path
import argparse,hashlib,json,shutil,zipfile,datetime,stat,re
from record_build_stage import verify as verify_stage
from record_boot_stage import verify_boot
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"host"))
from build_rates import FFT_LENGTH
ROOT=Path(__file__).resolve().parents[1]
SD_VECTOR_NAMES=dict(zero='ZERO',tone_pos_fs4='POS25',tone_neg_fs4='NEG25',burst_fs4='BURST',
  qpsk_sps4='QPSK4',qpsk_sps2='QPSK2',short512_boundary='SHORT512',negative_fullscale_dc='FULLNEG')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check():
    verify_stage('simulation')
    verify_stage('hardware')
    hw=json.loads((ROOT/'reports/hardware_validation.json').read_text())
    sw=json.loads((ROOT/'reports/software_validation.json').read_text())
    core=json.loads((ROOT/'reports/core_validation.json').read_text())
    python_tests=json.loads((ROOT/'reports/phase9_python_validation.json').read_text())
    parallel=json.loads((ROOT/'build/logs/core_parallel_manifest.json').read_text())
    assert python_tests['status']=='PASS' and len(python_tests['tests'])==7,'Python regressions incomplete'
    assert all(t['exit_code']==0 for t in python_tests['tests'])
    assert parallel['status']=='PASS' and len(parallel['groups'])==8,'Core case groups incomplete'
    assert core['maximum_analysis_latency_us']<=281.304,'Phase 10 must not regress Phase 9 RTL analysis latency'
    equivalent=json.loads((ROOT/'reports/phase10_equivalence.json').read_text())
    assert equivalent['status']=='PASS' and equivalent['spectrum_latency_cycles']==2127
    for name,digest in equivalent['files'].items():assert sha(ROOT/name)==digest,('Equivalence evidence changed',name)
    utilization=(ROOT/'reports/utilization_flat.rpt').read_text()
    def used(label):
        match=re.search(r'\|\s*'+re.escape(label)+r'\*?\s*\|\s*([\d.]+)',utilization)
        assert match,('Missing resource',label)
        return float(match[1])
    assert used('Slice LUTs')<31562 and used('LUT as Memory')<14667,'No LUT resource benefit'
    assert used('Block RAM Tile')<=124,'Phase 10 BRAM target failed'
    assert used('DSPs')<=49,'DSP usage regressed'
    assert hw['status']=='PASS' and hw['setup_slack_ns']>=0 and hw['hold_slack_ns']>=0,'Hardware timing failed'
    assert hw['cdc_critical']==0 and hw['unconstrained_internal_endpoints']==0
    assert core['status']=='PASS' and core['frequency_records']==64 and core['exact_fft_points']==64*FFT_LENGTH
    assert sw['status']=='BUILD_PASS' and sw['xsa_sha256']==sha(ROOT/'artifacts/iq_analyzer.xsa'),'Software targets another XSA'
    for name,digest in sw['artifacts'].items():assert sha(ROOT/'artifacts'/name)==digest,('ELF changed',name)
    for name,digest in sw['firmware_sources'].items():assert sha(ROOT/'firmware'/name)==digest,('Firmware changed',name)
    # Git checkout and archive extraction change modification times without
    # changing contents. The verified stage manifests above bind every source,
    # regression log, report and hardware artifact by SHA-256 instead.
    assert sha(ROOT/'artifacts/iq_analyzer.bit')==sha(ROOT/'build/board/iq_board.runs/impl_1/system_wrapper.bit')
    for script,marker in [('sim_core','CORE_PASS'),('sim_axi','AXI_PASS'),('sim_units','UNITS_PASS'),
                           ('sim_builder','BUILDER_PASS'),('sim_measurements','MEASUREMENTS_PASS'),
                           ('sim_digital_burst','DIGITAL_BURST_PASS'),('sim_spectrum_edges','SPECTRUM_EDGES_PASS')]:
        log=ROOT/'build/logs'/(script+'.log')
        assert log.is_file(),('Missing current regression',script)
        contents=log.read_text(errors='replace')
        assert marker in contents and 'Fatal:' not in contents,('Current regression failed',script)
    return hw,sw,core

def package():
    verify_boot()
    hw,sw,core=check();release=ROOT/'release';release.mkdir(exist_ok=True)
    sd=release/'sd_card';sd.mkdir(exist_ok=True);(sd/'VECTORS').mkdir(exist_ok=True)
    net=release/'ethernet_sd_card';net.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'artifacts/BOOT_sd.BIN',sd/'BOOT.BIN')
    shutil.copyfile(ROOT/'artifacts/BOOT_udp.BIN',net/'BOOT.BIN')
    names=SD_VECTOR_NAMES
    golden=json.loads((ROOT/'data/golden_results.json').read_text())['cases']
    assert [c['name'] for c in golden[:8]]==list(names),'SD fixture order and reference order differ'
    # Core fixtures contain four windows; physical replay retains a 32768-pair bank.
    for long,short in names.items():
        (sd/'VECTORS'/(short+'.BIN')).write_bytes((ROOT/'data/replay_vectors'/(long+'.bin')).read_bytes())
    manifest=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),board='Zybo Z7-20 / xc7z020clg400-1',
      hardware=hw,software=sw,simulation=core,board_tested=False,
      artifacts={name:sha(ROOT/'artifacts'/name) for name in ('iq_analyzer.bit','iq_analyzer.xsa','iq_udp.elf','iq_sd.elf',
        'zynq_fsbl.elf','ps7_init.tcl','BOOT.BIN','BOOT_sd.BIN','BOOT_udp.BIN')},
      source={p.relative_to(ROOT).as_posix():sha(p) for folder in ('rtl','constraints','scripts','firmware','tests','host','vendor/boards','config')
              for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts})
    acceptance_path=ROOT/'reports/phase10_acceptance.json'
    if acceptance_path.exists():
        from verify_phase10_evidence import verify as verify_acceptance
        acceptance=verify_acceptance(ROOT)
        assert all(acceptance['artifacts'][name]==digest for name,digest in manifest['artifacts'].items()),'Board acceptance targets another image'
        manifest.update(board_tested=True,board_validation_type='RAM_JTAG',physical_cold_boot=False,
                        acceptance_sha256=sha(acceptance_path))
        shutil.copyfile(acceptance_path,release/'phase10_acceptance.json')
    (release/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copyfile(ROOT/'reports/构建验证报告.md',release/'构建验证报告.md')
    evidence=release/'evidence';evidence.mkdir(exist_ok=True)
    for name in ('hardware_validation.json','software_validation.json','core_validation.json',
                 'simulation_provenance.json','hardware_provenance.json','boot_provenance.json',
                 'phase9_python_validation.json','phase2_latency_validation.json','phase10_equivalence.json',
                 'timing_summary.rpt','utilization_flat.rpt','cdc.rpt','drc.rpt','bus_skew.rpt','methodology.rpt'):
        shutil.copyfile(ROOT/'reports'/name,evidence/name)
    shutil.copyfile(ROOT/'PHASE10_STATUS.md',release/'PHASE10_STATUS.md')
    shutil.copyfile(ROOT/'build/vivado16k/iq_analyzer.sim/sim_1/behav/xsim/core_results.txt',evidence/'rtl_core_results.txt')
    for dest,mode in [(sd,'SD 自动运行 16 个有限采集测试并保存结果'),(net,'以太网交互与连续采集')]:
        (dest/'README.txt').write_text(f'Zybo Z7-20 / {mode}\n将本目录内容复制到已有 FAT32 分区根目录。\n每次仅使用一套 BOOT.BIN。\n本包通过构建检查；实板状态须查看与本包散列对应的验收记录。\n操作见工程根目录 README.md，当前状态见 PHASE10_STATUS.md。\n',encoding='utf-8')
        # Some vendor license files carry a Windows read-only attribute.
        # Keep their text intact, but permit rebuilding our generated copies.
        for p in (dest/'LICENSES').glob('*'):
            if p.is_file():p.chmod(stat.S_IREAD|stat.S_IWRITE)
        shutil.copytree(ROOT/'vendor/licenses',dest/'LICENSES',dirs_exist_ok=True,copy_function=shutil.copyfile)
        with zipfile.ZipFile(release/(dest.name+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for p in dest.rglob('*'):
                if p.is_file():z.write(p,p.relative_to(dest))
    with zipfile.ZipFile(release/'iq_analyzer_source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for folder in ('rtl','constraints','scripts','tests','firmware','host','docs','vendor','data','.github','config'):
            for p in (ROOT/folder).rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts:z.write(p,p.relative_to(ROOT))
        for name in ('README.md','CHANGELOG.md','VERSION.json','THIRD_PARTY_NOTICES.md','requirements.txt',
                     '.gitattributes','.gitignore','PHASE9_STATUS.md','PHASE10_STATUS.md','Open_IQ_Monitor.cmd','Run_Network_Tests.cmd','第二阶段优化实施方案.md','第三阶段优化实施方案.md'):
            z.write(ROOT/name,name)
    print('PACKAGE_PASS',release)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.check:check();print('PACKAGE_CHECK_PASS')
    else:package()
