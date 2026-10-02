"""Run using Vitis 2026.1: vitis -s scripts/build_software.py"""
from pathlib import Path
import shutil,os,stat,hashlib,json,re
import subprocess
ROOT=Path(__file__).resolve().parents[1]
xsa=ROOT/'artifacts/iq_analyzer.xsa'
if not xsa.exists():raise RuntimeError('Build timing-passed hardware before release software')
xsa_hash=hashlib.sha256(xsa.read_bytes()).hexdigest()
# Isolate platforms by hardware hash; never reuse the old pre-synthesis XSA.
workspace=ROOT/'build'/('vitis_'+xsa_hash[:12])
install=Path(os.environ.get('XILINX_VITIS',r'D:\VivadoMM\2026.1\Vitis'))
local_repo=ROOT/'build/local_sw_repo'
# Vitis 2026.1 ships both a Linux ELF named ``dtc`` and ``dtc.exe`` in its
# Windows bin directory.  Lopper can select the extensionless ELF first, so
# expose an isolated Windows-only host-tools directory to its subprocesses.
host_tools=ROOT/'build/host_tools'
host_tools.mkdir(parents=True,exist_ok=True)
dtc=host_tools/'dtc.exe'
shutil.copyfile(install/'bin/dtc.exe',dtc)
os.environ['PATH']=str(host_tools)+os.pathsep+os.environ.get('PATH','')
os.environ['DTC']=str(dtc)
os.environ['LOPPER_DTC']=str(dtc)
cpp=install/'gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-cpp.exe'
os.environ['LOPPER_CPP']=str(cpp)
dtc_check=subprocess.run([str(dtc),'--version'],capture_output=True,text=True,check=True)
cpp_check=subprocess.run([str(cpp),'--version'],capture_output=True,text=True,check=True)
print('DTC_READY',shutil.which('dtc'),dtc_check.stdout.strip())
print('CPP_READY',cpp,cpp_check.stdout.splitlines()[0])
import vitis
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

# The SDT lwIP template still calls init_timer() from init_platform() even
# when the xiltimer interval backend is disabled.  This registers an interrupt
# handler before the standalone IRQ path is ready; echo.c supplies the same
# lwIP cadence by polling the Zynq global timer instead.  Patch the local
# template so a fresh app receives the safe startup path on every build.
platform_template=local_repo/app_rel/'src/platform.c'
platform_text=platform_template.read_text(encoding='utf-8-sig')
platform_call='''#else
	init_timer();
#endif'''
platform_safe='''#else
	/* Timer polling is owned by echo.c; keep the SDT interval IRQ disabled. */
#endif'''
if platform_call in platform_text:
    platform_template.write_text(platform_text.replace(platform_call,platform_safe,1),encoding='utf-8')
elif platform_safe not in platform_text:
    raise RuntimeError('SDT timer call was not found in lwIP platform template')

# The Zybo Z7 RTL8211E is strapped on the GEM0 MDIO bus.  The SDT-generated
# lwIP adapter leaves PhyAddr at zero, scans a bus that can be temporarily
# unreadable during PHY reset, and then falls back to address zero.  AMD's
# fallback path assumes a Marvell PHY and can poll its reset bit forever.  Keep
# the vendor sources in the local repository, but make the board-specific
# startup deterministic and bounded so a missing link cannot hang the firmware.
physpeed=local_repo/lib_rel/'src/lwip-2.2.0/contrib/ports/xilinx/netif/xemacpsif_physpeed.c'
hw_adapter=local_repo/lib_rel/'src/lwip-2.2.0/contrib/ports/xilinx/netif/xemacpsif_hw.c'
physpeed_text=physpeed.read_text(encoding='utf-8-sig')
if 'IQ_ZYBO_PHY_RESET_POLL_LIMIT' not in physpeed_text:
    physpeed_text=physpeed_text.replace(
        '#define PHY_SPEED_AUTONEG\t\t0\t/**< Speed determined by auto-negotiation */',
        '#define PHY_SPEED_AUTONEG\t\t0\t/**< Speed determined by auto-negotiation */\n'
        '#define IQ_ZYBO_PHY_RESET_POLL_LIMIT 100000U')
    reset_pattern=(
        r'\t/\* Wait for reset to complete \*/\n'
        r'\twhile \(1\) \{\n'
        r'\t\tXEmacPs_PhyRead\(xemacpsp, phy_addr, IEEE_CONTROL_REG_OFFSET, &control\);\n'
        r'\t\tif \(!\(control & IEEE_CTRL_RESET_MASK\)\)\n'
        r'\t\t\tbreak;\n'
        r'\t\}')
    bounded_reset=(
        '\t/* Wait for reset to complete, but never block boot on a dead MDIO bus. */\n'
        '\tfor (u32_t reset_poll = 0; reset_poll < IQ_ZYBO_PHY_RESET_POLL_LIMIT; reset_poll++) {\n'
        '\t\tXEmacPs_PhyRead(xemacpsp, phy_addr, IEEE_CONTROL_REG_OFFSET, &control);\n'
        '\t\tif (!(control & IEEE_CTRL_RESET_MASK))\n'
        '\t\t\tbreak;\n'
        '\t\tif (reset_poll + 1U == IQ_ZYBO_PHY_RESET_POLL_LIMIT) {\n'
        '\t\t\txil_printf("PHY reset timeout at address %d\\r\\n", phy_addr);\n'
        '\t\t\treturn XST_FAILURE;\n'
        '\t\t}\n'
        '\t}')
    physpeed_text,count=re.subn(reset_pattern,lambda _match: bounded_reset,physpeed_text,count=2)
    if count != 2:
        raise RuntimeError(f'Expected two bounded PHY reset loops, replaced {count}')
    adi_pattern=(
        r'\twhile \(1\) \{\n'
        r'\t\tXEmacPs_PhyRead\(xemacpsp, phy_addr, IEEE_CONTROL_REG_OFFSET, &control\);\n'
        r'\t\tif \(control & IEEE_CTRL_RESET_MASK\)\n'
        r'\t\t\tcontinue;\n'
        r'\t\telse\n'
        r'\t\t\tbreak;\n'
        r'\t\}\n\n\t/\* Delay for PHY to be accessible \*/')
    bounded_adi=(
        '\t/* Delay for PHY to be accessible; bound the poll for a missing PHY. */\n'
        '\tfor (u32_t reset_poll = 0; reset_poll < IQ_ZYBO_PHY_RESET_POLL_LIMIT; reset_poll++) {\n'
        '\t\tXEmacPs_PhyRead(xemacpsp, phy_addr, IEEE_CONTROL_REG_OFFSET, &control);\n'
        '\t\tif (!(control & IEEE_CTRL_RESET_MASK))\n'
        '\t\t\tbreak;\n'
        '\t\tif (reset_poll + 1U == IQ_ZYBO_PHY_RESET_POLL_LIMIT) {\n'
        '\t\t\txil_printf("PHY reset timeout at address %d\\r\\n", phy_addr);\n'
        '\t\t\treturn XST_FAILURE;\n'
        '\t\t}\n'
        '\t}')
    physpeed_text,count=re.subn(adi_pattern,lambda _match: bounded_adi,physpeed_text,count=1)
    if count != 1:
        raise RuntimeError('Expected bounded ADI PHY reset loop')
    physpeed.write_text(physpeed_text,encoding='utf-8')

# A previous interrupted run could have applied the replacement through
# ``re.sub`` and interpreted the C escape sequence as a host newline.  Repair
# that generated text before it is copied into the BSP.
physpeed_text=physpeed.read_text(encoding='utf-8-sig')
repaired=re.sub(
    r'PHY reset timeout at address %d[\r\n]+", phy_addr\);',
    lambda _match: r'PHY reset timeout at address %d\r\n", phy_addr);',
    physpeed_text)
if repaired != physpeed_text:
    physpeed.write_text(repaired,encoding='utf-8')

hw_text=hw_adapter.read_text(encoding='utf-8-sig')
if 'IQ_ZYBO_DEFAULT_PHY_ADDR' not in hw_text:
    hw_text=hw_text.replace(
        '#ifndef SGMII_FIXED_LINK\n\tdetect_phy(xemacpsp);',
        '#ifndef SGMII_FIXED_LINK\n'
        '#define IQ_ZYBO_DEFAULT_PHY_ADDR 1U\n'
        '\tdetect_phy(xemacpsp);\n'
        '#ifdef SDT\n'
        '\t/* Allow the RTL8211E to settle after PS/GEM reset before fallback. */\n'
        '\tif (xemacpsp->Config.PhyAddr == 0U &&\n'
        '\t    xemacpsp->Config.BaseAddress == XPAR_XEMACPS_0_BASEADDR &&\n'
        '\t    phymapemac0[IQ_ZYBO_DEFAULT_PHY_ADDR] == FALSE) {\n'
        '\t\tfor (u32_t retry = 0; retry < 3U &&\n'
        '\t\t     phymapemac0[IQ_ZYBO_DEFAULT_PHY_ADDR] == FALSE; retry++) {\n'
        '\t\t\tsleep(1);\n'
        '\t\t\tdetect_phy(xemacpsp);\n'
        '\t\t}\n'
        '\t}\n'
        '#endif')
    hw_text=hw_text.replace(
        'link_speed = phy_setup_emacps(xemacpsp, 0);',
        'link_speed = phy_setup_emacps(xemacpsp, IQ_ZYBO_DEFAULT_PHY_ADDR);')
    hw_adapter.write_text(hw_text,encoding='utf-8')
# The Zybo GEM0 MDIO bus can mirror the RTL8211E at more than one address
# while the PS is coming out of reset.  Scanning and configuring every match
# leaves the final speed result as XST_FAILURE, which later trips the driver's
# operating-speed assertion.  Configure the known board PHY once and retain
# a valid MAC speed if autonegotiation has not settled yet.
hw_text=hw_adapter.read_text(encoding='utf-8-sig')
if 'IQ_ZYBO_DIRECT_PHY_INIT' not in hw_text:
    direct_pattern=(
        r'#ifndef SGMII_FIXED_LINK\n'
        r'#define IQ_ZYBO_DEFAULT_PHY_ADDR 1U\n'
        r'.*?'
        r'\n#else\n')
    direct_block=(
        '#ifndef SGMII_FIXED_LINK\n'
        '#define IQ_ZYBO_DEFAULT_PHY_ADDR 1U\n'
        '#define IQ_ZYBO_DIRECT_PHY_INIT 1\n'
        '\tMacConfig_SgmiiPcs(xemacpsp, IQ_ZYBO_DEFAULT_PHY_ADDR);\n'
        '\tlink_speed = phy_setup_emacps(xemacpsp, IQ_ZYBO_DEFAULT_PHY_ADDR);\n'
        '\tif (link_speed != 10U && link_speed != 100U && link_speed != 1000U) {\n'
        '\t\txil_printf("PHY autonegotiation incomplete; using 1000 Mbps MAC fallback\\r\\n");\n'
        '\t\tlink_speed = 1000U;\n'
        '\t}\n'
        '\tphyaddrforemac = IQ_ZYBO_DEFAULT_PHY_ADDR;\n'
        '#else\n')
    hw_text,count=re.subn(direct_pattern,lambda _match: direct_block,hw_text,count=1,flags=re.S)
    if count != 1:
        raise RuntimeError('Expected Zybo PHY scan block for deterministic replacement')
    hw_adapter.write_text(hw_text,encoding='utf-8')
print('LWIP_PHY_GUARD_PASS',physpeed,hw_adapter)

client=vitis.create_client()
try:
    client.log_level('DEBUG')
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
    domain.set_config(option='lib',lib_name='lwip220',param='lwip220_udp_block_tx',value='true')
    # Vitis 2026.1's SDT SCU-timer interval path can call XScuTimer_Stop
    # before the generated instance is ready.  The firmware supplies the
    # same 50 ms lwIP tick from the Zynq global timer, so leave the fragile
    # interrupt-backed interval timer disabled.
    domain.set_config(option='lib',lib_name='xiltimer',param='XILTIMER_en_interval_timer',value='false')
    domain.set_config(option='lib',lib_name='xiltimer',param='XILTIMER_tick_timer',value='None')
    platform.build()
    # Platform generation copies lwIP sources into the BSP.  Sync the guarded
    # sources after that copy and rebuild once so the static library contains
    # the board-specific PHY startup fix even when the Vitis workspace exists.
    generated=[]
    for name,source in (('xemacpsif_physpeed.c',physpeed),('xemacpsif_hw.c',hw_adapter)):
        candidates=[p for p in (workspace/'iq_platform').rglob(name)
                    if 'libsrc' in p.parts and 'lwip220' in p.parts]
        if not candidates:raise RuntimeError(f'Generated lwIP source missing: {name}')
        destination=candidates[0]
        shutil.copyfile(source,destination)
        generated.append(destination)
    platform.build()
    print('LWIP_BSP_SYNC_PASS',*generated)
    xpfm=workspace/'iq_platform/export/iq_platform/iq_platform.xpfm'
    if (workspace/'iq_udp').exists():app=client.get_component(name='iq_udp')
    else:app=client.create_app_component(name='iq_udp',platform=str(xpfm),domain='standalone_a9',template='lwip_echo_server')
    # Existing Vitis workspaces retain their generated application sources;
    # apply the same SDT timer guard before compiling the application.
    app_platform=workspace/'iq_udp/src/platform.c'
    app_platform_text=app_platform.read_text(encoding='utf-8-sig')
    if platform_call in app_platform_text:
        app_platform.write_text(app_platform_text.replace(platform_call,platform_safe,1),encoding='utf-8')
    elif platform_safe not in app_platform_text:
        raise RuntimeError('SDT timer call was not found in generated platform.c')
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
