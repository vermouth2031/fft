"""Run using Vitis 2026.1: vitis -s scripts/build_software.py"""
from pathlib import Path
import shutil,os,stat,hashlib,json
import vitis
ROOT=Path(__file__).resolve().parents[1]
xsa=ROOT/'artifacts/iq_analyzer.xsa'
if not xsa.exists():raise RuntimeError('Build timing-passed hardware before release software')
xsa_hash=hashlib.sha256(xsa.read_bytes()).hexdigest()
# Isolate platforms by hardware hash; never reuse the old pre-synthesis XSA.
workspace=ROOT/'build'/('vitis_'+xsa_hash[:12])
install=Path(os.environ.get('XILINX_VITIS',r'D:\VivadoMM\2026.1\Vitis'))
local_repo=ROOT/'build/local_sw_repo'
# 2026.1's dependency validator now treats a flat map as ALL-required, but
# installed lwIP metadata lists alternative MACs in a flat map. Scope a local
# copy to the actual Zybo GEM + TTC hardware; never alter the AMD installation.
lib_rel=Path('ThirdParty/sw_services/lwip220_v1_4')
app_rel=Path('lib/sw_apps/lwip_echo_server')
for rel in (lib_rel,app_rel):
    if not (local_repo/rel).exists():shutil.copytree(install/'data/embeddedsw'/rel,local_repo/rel,copy_function=shutil.copyfile)
    for p in (local_repo/rel).rglob('*'):
        if p.is_file():p.chmod(stat.S_IREAD|stat.S_IWRITE)
lib_yaml=local_repo/lib_rel/'data/lwip220.yaml'
text=lib_yaml.read_text(encoding='utf-8-sig');begin=text.index('\ndepends:');end=text.index('\nexamples:',begin)
lib_yaml.write_text(text[:begin]+'\ndepends:\n  emacps: [reg, interrupts]\n'+text[end:],encoding='utf-8')
app_yaml=local_repo/app_rel/'data/lwip_echo_server.yaml'
text=app_yaml.read_text(encoding='utf-8-sig');begin=text.index('\ndepends:');end=text.index('\ndepends_libs:',begin)
text=text[:begin]+'\ndepends:\n  emacps: [reg, interrupts]\n  scutimer: [reg, interrupts]\n'+text[end:]
app_yaml.write_text(text.replace('lwip220_dhcp: true','lwip220_dhcp: false').replace('lwip220_lwip_dhcp_does_acd_check: true','lwip220_lwip_dhcp_does_acd_check: false'),encoding='utf-8')
app_cmake=local_repo/app_rel/'src/lwip_echo_server.cmake'
text=app_cmake.read_text(encoding='utf-8-sig')
if 'TOTAL_TIMER_INSTANCES ${SCUTIMER_NUM_DRIVER_INSTANCES}' not in text:
    text=text.replace('list(APPEND TOTAL_TIMER_INSTANCES ${TTCPS_NUM_DRIVER_INSTANCES})',
        'list(APPEND TOTAL_TIMER_INSTANCES ${TTCPS_NUM_DRIVER_INSTANCES})\nlist(APPEND TOTAL_TIMER_INSTANCES ${SCUTIMER_NUM_DRIVER_INSTANCES})')
app_cmake.write_text(text,encoding='utf-8')
client=vitis.create_client()
try:
    client.set_workspace(path=str(workspace))
    client.set_embedded_sw_repo(level='LOCAL',path=str(local_repo))
    if (workspace/'iq_platform').exists():platform=client.get_component(name='iq_platform')
    else:platform=client.create_platform_component(name='iq_platform',hw_design=str(xsa),
        os='standalone',cpu='ps7_cortexa9_0',domain_name='standalone_a9',generate_dtb=False)
    domain=platform.get_domain(name='standalone_a9')
    if 'lwip220' not in str(domain.get_libs()):domain.set_lib(lib_name='lwip220')
    if 'xilffs' not in str(domain.get_libs()):domain.set_lib(lib_name='xilffs')
    # META.JSON has a four-character extension, so enable the static LFN buffer.
    domain.set_config(option='lib',lib_name='xilffs',param='XILFFS_use_lfn',value='1')
    domain.set_config(option='lib',lib_name='xilffs',param='XILFFS_use_mkfs',value='false')
    domain.set_config(option='lib',lib_name='lwip220',param='lwip220_dhcp',value='false')
    domain.set_config(option='lib',lib_name='lwip220',param='lwip220_lwip_dhcp_does_acd_check',value='false')
    domain.set_config(option='lib',lib_name='lwip220',param='lwip220_pbuf_pool_size',value='2048')
    domain.set_config(option='lib',lib_name='xiltimer',param='XILTIMER_en_interval_timer',value='true')
    platform.build()
    xpfm=workspace/'iq_platform/export/iq_platform/iq_platform.xpfm'
    if (workspace/'iq_udp').exists():app=client.get_component(name='iq_udp')
    else:app=client.create_app_component(name='iq_udp',platform=str(xpfm),domain='standalone_a9',template='lwip_echo_server')
    # Keep generated template/platform code; replace the protocol implementation.
    shutil.copyfile(ROOT/'firmware/echo.c',workspace/'iq_udp/src/echo.c')
    app.set_app_config(key='USER_COMPILE_OPTIMIZATION_LEVEL',values=['-O2'])
    app.build()
    elfs=list((workspace/'iq_udp').rglob('iq_udp.elf'))
    if not elfs:raise RuntimeError('Firmware build did not produce iq_udp.elf')
    shutil.copyfile(elfs[0],ROOT/'artifacts/iq_udp.elf')
    fsbl=list((workspace/'iq_platform').rglob('*fsbl*.elf'))
    if not fsbl:raise RuntimeError('FSBL missing')
    shutil.copyfile(fsbl[0],ROOT/'artifacts/zynq_fsbl.elf')
    if (workspace/'iq_sd').exists():sd=client.get_component(name='iq_sd')
    else:sd=client.create_app_component(name='iq_sd',platform=str(xpfm),domain='standalone_a9',template='empty_application')
    shutil.copyfile(ROOT/'firmware/sd_main.c',workspace/'iq_sd/src/main.c')
    sd.set_app_config(key='USER_COMPILE_OPTIMIZATION_LEVEL',values=['-O2'])
    sd.set_app_config(key='USER_LINK_LIBRARIES',values=['xilffs','xiltimer'])
    sd.build()
    sd_elfs=list((workspace/'iq_sd').rglob('iq_sd.elf'))
    if not sd_elfs:raise RuntimeError('SD application ELF missing')
    shutil.copyfile(sd_elfs[0],ROOT/'artifacts/iq_sd.elf')
    (ROOT/'reports/software_validation.json').write_text(json.dumps(dict(status='BUILD_PASS',
        xsa_sha256=xsa_hash,workspace=str(workspace),board_tested=False,
        artifacts={n:hashlib.sha256((ROOT/'artifacts'/n).read_bytes()).hexdigest()
                   for n in ('iq_udp.elf','iq_sd.elf','zynq_fsbl.elf')},
        firmware_sources={n:hashlib.sha256((workspace/p).read_bytes()).hexdigest()
                          for n,p in [('echo.c','iq_udp/src/echo.c'),('sd_main.c','iq_sd/src/main.c')]}),indent=2)+'\n')
    print('SOFTWARE_BUILD_PASS',elfs[0])
finally:vitis.dispose()
