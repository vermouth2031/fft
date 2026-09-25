"""One bounded fix for the measured combined-build reset fanout path."""
from pathlib import Path
import json
import shutil
import subprocess
import zipfile

root=Path('D:/fft/iq_phase4_combined')
archive=root/'build/phase4_combined_v1_rejected'
archive.mkdir(exist_ok=False)
report=json.loads((root/'reports/hardware_validation.json').read_text())
assert report['setup_slack_ns']==.078
for folder in ('reports','build/logs','build/config'):
    shutil.copytree(root/folder,archive/folder,copy_function=shutil.copy2)
for name in ('build/phase4_sim_console.log','build/phase4_hardware_console.log','build/phase4_software_console.log'):
    shutil.copy2(root/name,archive/Path(name).name)
with zipfile.ZipFile(archive/'source.zip','x',zipfile.ZIP_DEFLATED) as z:
    for folder in ('rtl','tests','scripts','config','constraints','host','firmware'):
        for p in (root/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:z.write(p,p.relative_to(root))
path=root/'rtl/spectrum_measure.sv';text=path.read_bytes()
old=(b'     for(j=0;j<8;j=j+1)begin\r\n'
     b'       power_pipe[j]<=0;pair_prefix[j]<=0;quad_prefix[j]<=0;prefix[j]<=0;cdf_bin[j]<=0;\r\n'
     b'     end\r\n'
     b'     for(j=0;j<4;j=j+1)pair_max[j]<=0;\r\n'
     b'     for(j=0;j<2;j=j+1)quad_max[j]<=0;\r\n'
     b'     octet_max<=0;\r\n')
assert text.count(old)==1
text=text.replace(old,b'     // Datapath contents are ignored until their reset-cleared valid bits\r\n'
                     b'     // advance. Leave these wide payload registers unreset to remove\r\n'
                     b'     // the measured synchronized-reset fanout bottleneck.\r\n')
path.write_bytes(text)
path=root/'tests/tb_spectrum_edges.sv';text=path.read_bytes()
assert text.count(b' if(!rst)begin')==1
text=text.replace(b' reg rst=1,valid=0,last=0,snap_request=0;',
                  b' reg rst=1,valid=0,last=0,snap_request=0;\r\n reg checking=0;')
text=text.replace(b' if(!rst)begin',b' if(!rst&&checking)begin')
old=b'   repeat(8)@(negedge clk);rst=0;\r\n   for(f=0;f<CASES;f=f+1)begin'
new=(b'   repeat(8)@(negedge clk);rst=0;\r\n'
     b'   // Interrupt a nonzero scan with live payload in every prefix stage.\r\n'
     b'   drive_frame(4);@(negedge clk);valid=0;last=0;\r\n'
     b'   wait(dut.compare_valid);repeat(4)@(negedge clk);\r\n'
     b'   rst=1;snap_request=0;repeat(8)@(negedge clk);rst=0;\r\n'
     b'   repeat(1200)begin\r\n'
     b'     @(negedge clk);\r\n'
     b'     if(rv||snap_we||snap_done||fault)$fatal(1,"Stale spectrum output after reset");\r\n'
     b'   end\r\n'
     b'   checking=1;\r\n'
     b'   $display("SPECTRUM_MIDSCAN_RESET_PASS");\r\n'
     b'   for(f=0;f<CASES;f=f+1)begin')
assert text.count(old)==1;text=text.replace(old,new);path.write_bytes(text)
(archive/'decision.json').write_text(json.dumps(dict(status='NOT_PROMOTED',hardware=report,
    partial_core_cases=5,simulation_interrupted=True,software_interrupted=True,
    fix='Remove reset only from validity-masked wide spectrum payloads; retain all control resets',
    test='Reset during active prefix scan; require no stale outputs, then all 36 cases and 6144 snapshot words'),indent=2))
subprocess.run(['python','scripts/phase4_build_config.py'],cwd=root,check=True)
print('TARGETED_RESET_FIX_PREPARED')
