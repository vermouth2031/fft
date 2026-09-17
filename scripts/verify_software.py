"""Check source/build/artifact correspondence before packaging either firmware."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=R/'reports/software_validation.json';v=json.loads(p.read_text())
workspace=Path(v['workspace']);assert v['xsa_sha256']==sha(R/'artifacts/iq_analyzer.xsa')
sources={}
for name,app,source in [('echo.c','iq_udp','echo.c'),('sd_main.c','iq_sd','main.c')]:
    compiled=workspace/app/'src'/source;elf=workspace/app/'build'/(app+'.elf')
    assert sha(compiled)==sha(R/'firmware'/name),('Source changed',name)
    assert elf.stat().st_mtime>=compiled.stat().st_mtime,('ELF predates source',name)
    assert sha(elf)==v['artifacts'][app+'.elf']==sha(R/'artifacts'/(app+'.elf'))
    sources[name]=sha(compiled)
v['firmware_sources']=sources
p.write_text(json.dumps(v,indent=2)+'\n')
print('SOFTWARE_CORRESPONDENCE_PASS')
