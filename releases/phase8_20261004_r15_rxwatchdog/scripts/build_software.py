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
link_detect_block='''\t/* For detecting Ethernet phy link status periodically */
\tif (DetectEthLinkStatus == ETH_LINK_DETECT_INTERVAL) {
\t\teth_link_detect(echo_netif);
\t\tDetectEthLinkStatus = 0;
\t}'''
link_detect_safe='''\t/* The Zybo RGMII PHY is initialized once by the generated adapter.
\t * Re-running the template detector can restart RTL8211E autonegotiation
\t * while its status bit is settling and flap the host link. */
\t(void)DetectEthLinkStatus;'''
if platform_call in platform_text:
    platform_template.write_text(platform_text.replace(platform_call,platform_safe,1),encoding='utf-8')
elif platform_safe not in platform_text:
    raise RuntimeError('SDT timer call was not found in lwIP platform template')
platform_text=platform_template.read_text(encoding='utf-8-sig')
if link_detect_block in platform_text:
    platform_template.write_text(platform_text.replace(link_detect_block,link_detect_safe,1),encoding='utf-8')
elif link_detect_safe not in platform_text:
    raise RuntimeError('lwIP link detector block was not found in platform template')

# The Zybo Z7 RTL8211E is strapped on the GEM0 MDIO bus.  The SDT-generated
# lwIP adapter leaves PhyAddr at zero, scans a bus that can be temporarily
# unreadable during PHY reset, and then falls back to address zero.  AMD's
# fallback path assumes a Marvell PHY and can poll its reset bit forever.  Keep
# the vendor sources in the local repository, but make the board-specific
# startup deterministic and bounded so a missing link cannot hang the firmware.
physpeed=local_repo/lib_rel/'src/lwip-2.2.0/contrib/ports/xilinx/netif/xemacpsif_physpeed.c'
hw_adapter=local_repo/lib_rel/'src/lwip-2.2.0/contrib/ports/xilinx/netif/xemacpsif_hw.c'
physpeed_text=physpeed.read_text(encoding='utf-8-sig')
# SDT can leave Config.PhyType unset for the board-specific GEM.  The vendor
# SGMII helper dereferences it before checking the MAC mode, which raises an
# ARM data abort during Ethernet startup.  Keep this replacement idempotent so
# a fresh local repository and an existing Vitis workspace receive the guard.
sgmii_unsafe='if (!strcmp(PhyType, "sgmii") && !isphy_pcspma_external(xemacpsp, phy_addr)){'
sgmii_safe='if (PhyType != NULL && !strcmp(PhyType, "sgmii") &&\n\t    !isphy_pcspma_external(xemacpsp, phy_addr)){'
if sgmii_unsafe in physpeed_text:
    physpeed_text=physpeed_text.replace(sgmii_unsafe,sgmii_safe,1)
    physpeed.write_text(physpeed_text,encoding='utf-8')
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
# Normalize speeds used by both initial setup and link recovery.  The vendor
# PHY routine can transiently return XST_FAILURE while autonegotiation settles;
# passing that value into XEmacPs_SetOperatingSpeed triggers an assert loop.
safe_speed_helper='''
static u32_t iq_safe_link_speed(u32_t speed)
{
\treturn (speed == 10U || speed == 100U || speed == 1000U) ? speed : 1000U;
}
'''
if 'iq_safe_link_speed' not in hw_text:
    hw_text=hw_text.replace('u32_t link_speed = 100;\n',
                            'u32_t link_speed = 100;\n'+safe_speed_helper,1)
    hw_text=hw_text.replace('XEmacPs_SetOperatingSpeed(xemacpsp, link_speed);',
                            'XEmacPs_SetOperatingSpeed(xemacpsp, iq_safe_link_speed(link_speed));')
    hw_adapter.write_text(hw_text,encoding='utf-8')
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
    # Keep NO_SYS receive callbacks responsive; the GEM driver retains each
    # submitted pbuf until TX completion, and the main loop polls TX cleanup.
    domain.set_config(option='lib',lib_name='lwip220',param='lwip220_udp_block_tx',value='false')
    # The lwip_echo_server template requires the interval timer to be enabled
    # while the application component is created.  Create that component
    # first, then disable the fragile interrupt-backed path before the final
    # BSP build; echo.c supplies the same 50 ms cadence by polling the global
    # timer.
    domain.set_config(option='lib',lib_name='xiltimer',param='XILTIMER_en_interval_timer',value='true')
    domain.set_config(option='lib',lib_name='xiltimer',param='XILTIMER_tick_timer',value='ps7_scutimer_0')
    platform.build()
    xpfm=workspace/'iq_platform/export/iq_platform/iq_platform.xpfm'
    if (workspace/'iq_udp').exists():
        app=client.get_component(name='iq_udp')
    else:
        app=client.create_app_component(name='iq_udp',platform=str(xpfm),domain='standalone_a9',template='lwip_echo_server')
    # Vitis 2026.1's SDT SCU-timer interval path can call XScuTimer_Stop
    # before the generated instance is ready.  Disable it for the final BSP.
    domain.set_config(option='lib',lib_name='xiltimer',param='XILTIMER_en_interval_timer',value='false')
    domain.set_config(option='lib',lib_name='xiltimer',param='XILTIMER_tick_timer',value='None')
    # Vitis 2026.1's SDT interrupt wrapper can inherit a stale XScuGic
    # instance when a processor-only JTAG reset leaves DDR contents intact.
    # An old IsReady marker paired with a small/invalid Config pointer makes
    # XScuGic_Connect write through address 0 and raises a data abort before
    # GEM RX/TX is enabled.  Force the wrapper back through CfgInitialize when
    # that impossible pointer state is observed.
    interrupt_guard = '''#if defined(XPAR_SCUGIC)
\tif (XScuGicInstance.IsReady == XIL_COMPONENT_IS_READY &&
\t    (XScuGicInstance.Config == NULL ||
\t     (UINTPTR)XScuGicInstance.Config < 0x00100000U)) {
\t\tXScuGicInstance.IsReady = 0U;
\t\tScuGicInitialized = 0;
\t}
#endif
'''
    for interrupt_source in (workspace/'iq_platform').rglob('xinterrupt_wrap.c'):
        interrupt_text=interrupt_source.read_text(encoding='utf-8-sig')
        if 'ScuGicInitialized = 0;' not in interrupt_text:
            marker='int XConfigInterruptCntrl(UINTPTR IntcParent)\n{\n'
            if marker not in interrupt_text:
                raise RuntimeError(f'GIC init function missing in {interrupt_source}')
            interrupt_source.write_text(
                interrupt_text.replace(marker,marker+interrupt_guard,1),
                encoding='utf-8')
    for adapter_source in (workspace/'iq_platform').rglob('xadapter.c'):
        adapter_text=adapter_source.read_text(encoding='utf-8-sig')
        adapter_marker='XEmacPs_SetOperatingSpeed(xemacp, link_speed);'
        adapter_guard='''if (link_speed != 10U && link_speed != 100U && link_speed != 1000U) {
\t\t\t\t\t/* Keep link recovery alive while PHY autonegotiation settles. */
\t\t\t\t\tlink_speed = 1000U;
\t\t\t\t}
\t\t\t\t'''
        if 'Keep link recovery alive while PHY autonegotiation settles.' not in adapter_text:
            marker_index=adapter_text.find(adapter_marker)
            if marker_index < 0:
                raise RuntimeError(f'GEM link recovery path missing in {adapter_source}')
            line_start=adapter_text.rfind('\n',0,marker_index)+1
            indent=adapter_text[line_start:marker_index]
            guard=adapter_guard.replace('\t\t\t\t',indent)
            adapter_text=adapter_text[:line_start]+guard+adapter_text[line_start:]
            adapter_source.write_text(adapter_text,encoding='utf-8')
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
    # In NO_SYS polling mode the vendor adapter normally expects the GEM RX
    # interrupt to invoke emacps_recv_handler().  GEM interrupts are disabled
    # for this application, so feed completed RX descriptors into lwIP at the
    # start of each xemacpsif_input() poll instead.
    for input_source in (workspace/'iq_platform').rglob('xemacpsif.c'):
        if 'libsrc' not in input_source.parts or 'lwip220' not in input_source.parts:
            continue
        input_text=input_source.read_text(encoding='utf-8-sig')
        poll_marker='IQ_NO_SYS_POLLING_RX_HANDLER'
        tx_poll_marker='IQ_NO_SYS_POLLING_TX_CLEANUP'
        if tx_poll_marker not in input_text:
            tx_poll_call='''#if NO_SYS
	/* IQ_NO_SYS_POLLING_TX_CLEANUP */
	/* Reclaim completed TX descriptors while GEM IRQs are off. */
	struct xemac_s *poll_xemac = (struct xemac_s *)netif->state;
	xemacpsif_s *poll_xemacpsif = (xemacpsif_s *)poll_xemac->state;
	xemacps_process_sent_bds(poll_xemacpsif,
		&XEmacPs_GetTxRing(&poll_xemacpsif->emacps));
#endif
'''
            function_index=input_text.find('s32_t xemacpsif_input(struct netif *netif)')
            protect_marker='\tSYS_ARCH_PROTECT(lev);'
            protect_index=input_text.find(protect_marker,function_index)
            if function_index < 0 or protect_index < 0:
                raise RuntimeError(f'xemacpsif TX polling insertion point missing in {input_source}')
            input_text=input_text[:protect_index]+tx_poll_call+input_text[protect_index:]
            input_source.write_text(input_text,encoding='utf-8')
            generated.append(input_source)
        # The blocking TX path also polls the completed descriptors after the
        # send call.  Keep the ring pointer initialized on every path; the
        # vendor template only assigned it in the low-space recovery branch.
        tx_ring_init_marker='IQ_NO_SYS_TX_RING_INIT'
        if tx_ring_init_marker not in input_text:
            tx_ring_init='''\t/* IQ_NO_SYS_TX_RING_INIT */
\ttxring = &(XEmacPs_GetTxRing(&xemacpsif->emacps));
'''
            function_index=input_text.find('static err_t low_level_output(struct netif *netif, struct pbuf *p)')
            protect_marker='\tSYS_ARCH_PROTECT(lev);'
            protect_index=input_text.find(protect_marker,function_index)
            if function_index < 0 or protect_index < 0:
                raise RuntimeError(f'xemacps TX ring initialization point missing in {input_source}')
            input_text=input_text[:protect_index]+tx_ring_init+input_text[protect_index:]
            input_source.write_text(input_text,encoding='utf-8')
            generated.append(input_source)
        blocking_marker='IQ_NO_SYS_BLOCKING_TX_CLEANUP'
        if blocking_marker not in input_text:
            blocking_call='''\t\twhile(notifyinfo[to_block_index] == 1) {
			/* IQ_NO_SYS_BLOCKING_TX_CLEANUP */
			xemacps_process_sent_bds(xemacpsif, txring);
			usleep(1);
			notfifyblocksleepcntr--;
			if (notfifyblocksleepcntr <= 0) {
				err = ERR_TIMEOUT;
				break;
			}
		}'''
            blocking_pattern='''\t\twhile(notifyinfo[to_block_index] == 1) {
			usleep(1);
			notfifyblocksleepcntr--;
			if (notfifyblocksleepcntr <= 0) {
				err = ERR_TIMEOUT;
				break;
			}
		}'''
            if blocking_pattern not in input_text:
                raise RuntimeError(f'xemacps blocking TX polling insertion point missing in {input_source}')
            input_text=input_text.replace(blocking_pattern,blocking_call,1)
            input_source.write_text(input_text,encoding='utf-8')
            generated.append(input_source)
        if poll_marker not in input_text:
            poll_call='''#if NO_SYS
	/* IQ_NO_SYS_POLLING_RX_HANDLER */
	emacps_recv_handler(netif->state);
#endif
	SYS_ARCH_PROTECT(lev);'''
            function_index=input_text.find('s32_t xemacpsif_input(struct netif *netif)')
            protect_marker='\tSYS_ARCH_PROTECT(lev);'
            protect_index=input_text.find(protect_marker,function_index)
            if function_index < 0 or protect_index < 0:
                raise RuntimeError(f'xemacpsif polling insertion point missing in {input_source}')
            input_text=input_text[:protect_index]+poll_call+input_text[protect_index+len(protect_marker):]
            input_source.write_text(input_text,encoding='utf-8')
            generated.append(input_source)
    # This firmware uses lwIP NO_SYS=1 and polls xemacif_input() from its main
    # loop.  Vitis 2026.1's SDT adapter still enables the GEM interrupt in
    # init_dma(), which can dispatch through a stale GIC context after a JTAG
    # processor reset and trip XEmacPs_IntrHandler's IsReady assertion.  Keep
    # the GEM interrupt path compiled for threaded users, but leave it disabled
    # for this polling application.
    for dma_source in (workspace/'iq_platform').rglob('xemacpsif_dma.c'):
        if 'libsrc' not in dma_source.parts or 'lwip220' not in dma_source.parts:
            continue
        dma_text=dma_source.read_text(encoding='utf-8-sig')
        malformed_guard='#endif#endif /* !NO_SYS */'
        if malformed_guard in dma_text:
            dma_text=dma_text.replace(malformed_guard,'#endif\n#endif /* !NO_SYS */')
            dma_source.write_text(dma_text,encoding='utf-8')
            generated.append(dma_source)
        # The GEM RX ``NEW`` bit is owned by hardware: software clears it when
        # returning a descriptor, and hardware sets it after receiving a
        # frame.  Do not set it while replenishing buffers.  Repair workspaces
        # produced by the earlier experimental patch before compiling.
        patched_last='XEmacPs_BdSetAddressRx(rxbd, ((UINTPTR)p->payload | XEMACPS_RXBUF_NEW_MASK | XEMACPS_RXBUF_WRAP_MASK));'
        patched_regular='XEmacPs_BdSetAddressRx(rxbd, ((UINTPTR)p->payload | XEMACPS_RXBUF_NEW_MASK));'
        original_last='XEmacPs_BdWrite(rxbd, XEMACPS_BD_ADDR_OFFSET, ((UINTPTR)p->payload | XEMACPS_RXBUF_WRAP_MASK));'
        original_regular='XEmacPs_BdWrite(rxbd, XEMACPS_BD_ADDR_OFFSET, (UINTPTR)p->payload);'
        repaired_dma=dma_text.replace(patched_last,original_last,1).replace(patched_regular,original_regular,1)
        repaired_dma=repaired_dma.replace('/* IQ_NO_SYS_RX_NEW_BIT_GUARD */\n\nvoid emacps_recv_handler(void *arg)',
                                            'void emacps_recv_handler(void *arg)',1)
        if repaired_dma != dma_text:
            dma_text=repaired_dma
            dma_source.write_text(dma_text,encoding='utf-8')
            generated.append(dma_source)
        rx_watchdog_marker='IQ_NO_SYS_PERIODIC_RX_WATCHDOG'
        if '#include "xtime_l.h"' in dma_text:
            dma_text=dma_text.replace('#include "xtime_l.h"','#include "xiltimer.h"',1)
            dma_source.write_text(dma_text,encoding='utf-8')
            generated.append(dma_source)
        if rx_watchdog_marker not in dma_text:
            include_marker='#include "xstatus.h"'
            if '#include "xiltimer.h"' not in dma_text:
                if include_marker not in dma_text:
                    raise RuntimeError(f'GEM RX watchdog include point missing in {dma_source}')
                dma_text=dma_text.replace(include_marker,include_marker+'\n#include "xiltimer.h"',1)
            rx_poll='''\tif (gigeversion <= 2) {
\t\t\tresetrx_on_no_rxdata(xemacpsif);
\t}'''
            rx_periodic='''\tif (gigeversion <= 2) {
#if NO_SYS
\t\t/* IQ_NO_SYS_PERIODIC_RX_WATCHDOG */
\t\t/* The rev-2 workaround reads clear-on-read counters; bound its cadence. */
\t\tstatic XTime rx_watchdog_last;
\t\tXTime rx_watchdog_now;
\t\tXTime_GetTime(&rx_watchdog_now);
\t\tif ((rx_watchdog_now - rx_watchdog_last) >=
\t\t    ((XTime)XPAR_CPU_CORE_CLOCK_FREQ_HZ / 2U)) {
\t\t\trx_watchdog_last = rx_watchdog_now;
\t\t\tresetrx_on_no_rxdata(xemacpsif);
\t\t}
#else
\t\tresetrx_on_no_rxdata(xemacpsif);
#endif
\t}'''
            if rx_poll not in dma_text:
                raise RuntimeError(f'GEM revision-2 RX watchdog call missing in {dma_source}')
            dma_text=dma_text.replace(rx_poll,rx_periodic,1)
            dma_source.write_text(dma_text,encoding='utf-8')
            generated.append(dma_source)
        irq_marker='IQ_NO_SYS_POLLING_GEM_IRQ_GUARD'
        if irq_marker not in dma_text:
            # Vitis changes whitespace around this generated block between
            # releases. Locate the stable API call and wrap the complete
            # SDT/non-SDT enable block instead of matching a comment layout.
            sdt_call='XSetupInterruptSystem(&xemacpsif->emacps, &XEmacPs_IntrHandler,'
            non_sdt_call='XScuGic_EnableIntr(INTC_DIST_BASE_ADDR, (u32) xtopologyp->scugic_emac_intr);'
            sdt_index=dma_text.find(sdt_call)
            non_sdt_index=dma_text.find(non_sdt_call)
            if sdt_index < 0 or non_sdt_index < 0:
                raise RuntimeError(f'GEM interrupt enable API calls missing in {dma_source}')
            block_start=dma_text.rfind('/*',0,sdt_index)
            comment_end=dma_text.find('*/',block_start)
            if block_start < 0 or comment_end < 0:
                block_start=sdt_index
            else:
                block_start=dma_text.rfind('\n',0,block_start)+1
            return_index=dma_text.find('\n\treturn 0;',non_sdt_index)
            if return_index < 0:
                return_index=dma_text.find('\nreturn 0;',non_sdt_index)
            if return_index < 0 or return_index <= block_start:
                raise RuntimeError(f'GEM interrupt enable block terminator missing in {dma_source}')
            dma_text=(dma_text[:block_start]
                      +'\t/* IQ_NO_SYS_POLLING_GEM_IRQ_GUARD */\n'
                      +'#if !NO_SYS\n'
                      +dma_text[block_start:return_index]
                      +'\n#endif /* !NO_SYS */'
                      +dma_text[return_index:])
            dma_source.write_text(dma_text,encoding='utf-8')
            generated.append(dma_source)
    platform.build()
    print('LWIP_BSP_SYNC_PASS',*generated)
    # Existing Vitis workspaces retain their generated application sources;
    # apply the same SDT timer guard before compiling the application.
    app_platform=workspace/'iq_udp/src/platform.c'
    app_platform_text=app_platform.read_text(encoding='utf-8-sig')
    if platform_call in app_platform_text:
        app_platform_text=app_platform_text.replace(platform_call,platform_safe,1)
    if link_detect_block in app_platform_text:
        app_platform_text=app_platform_text.replace(link_detect_block,link_detect_safe,1)
    if app_platform_text != app_platform.read_text(encoding='utf-8-sig'):
        app_platform.write_text(app_platform_text,encoding='utf-8')
    if platform_safe not in app_platform_text:
        raise RuntimeError('SDT timer call was not found in generated platform.c')
    if link_detect_safe not in app_platform_text:
        raise RuntimeError('Generated platform.c link detector guard was not applied')
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
