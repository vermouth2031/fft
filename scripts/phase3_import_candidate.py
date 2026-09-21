"""Import an already-tested isolated candidate without relabeling old evidence."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
from record_build_stage import ROOT,sha

SOURCES=('rtl/spectrum_measure.sv','tests/tb_core.sv','tests/tb_spectrum_edges.sv',
         'scripts/build_board.tcl','scripts/rebuild_board.tcl','scripts/phase3_replication_hook.tcl',
         'scripts/record_build_stage.py','scripts/analyze_latency.py')


def require(ok,message):
    if not ok:raise ValueError(message)


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--backup',type=Path,required=True);a=p.parse_args()
    candidate=a.candidate.resolve();backup=a.backup.resolve()
    require(candidate!=ROOT and candidate.is_dir(),'Expected a distinct completed candidate project')
    require(backup.is_relative_to(ROOT/'build') and not backup.exists(),'Backup must be a new project build directory')
    manifests={}
    for stage in ('simulation','hardware'):
        subprocess.run([sys.executable,'scripts/record_build_stage.py',stage,'--check'],cwd=candidate,check=True)
        manifests[stage]=json.loads((candidate/'reports'/f'{stage}_provenance.json').read_text())
    software=json.loads((candidate/'reports/software_validation.json').read_text())
    require(software['status']=='BUILD_PASS','Candidate software is incomplete')
    require(software['xsa_sha256']==sha(candidate/'artifacts/iq_analyzer.xsa'),'Candidate software XSA mismatch')
    for name,digest in software['artifacts'].items():require(sha(candidate/'artifacts'/name)==digest,'Candidate ELF mismatch')
    for manifest in manifests.values():
        for name,digest in manifest['inputs'].items():
            if name not in SOURCES:
                require((ROOT/name).is_file() and sha(ROOT/name)==digest,'Unapproved source/input difference: '+name)
    backup.mkdir(parents=True)
    for directory in ('artifacts','reports','build/logs'):
        shutil.copytree(ROOT/directory,backup/directory,copy_function=shutil.copy2)
    for name in SOURCES:
        if (ROOT/name).exists():
            saved=backup/'source'/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,saved)
    transfer={}
    def copy(name):
        source=candidate/name;destination=ROOT/name
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
        digest=sha(source);require(sha(destination)==digest,'Copy mismatch: '+name)
        transfer[name]=digest
    for name in SOURCES:copy(name)
    # Both resolved move endpoints are checked within this project. Preserve the
    # complete old board project; never mix a new bit with an old implementation.
    board=(ROOT/'build/board').resolve();old_board=(backup/'board_project').resolve()
    require(board.is_relative_to(ROOT) and old_board.is_relative_to(ROOT) and not old_board.exists(),'Unsafe board project move')
    board.rename(old_board)
    shutil.copytree(candidate/'build/board',board,copy_function=shutil.copy2)
    for name in ('iq_analyzer.bit','iq_analyzer.xsa','iq_udp.elf','iq_sd.elf','zynq_fsbl.elf'):
        copy('artifacts/'+name)
    paths={'reports/software_validation.json','build/vivado/iq_analyzer.sim/sim_1/behav/xsim/core_results.txt'}
    for stage,manifest in manifests.items():
        paths.add(f'reports/{stage}_provenance.json');paths.update(manifest['evidence'])
    paths.update('reports/'+name for name in ('utilization.rpt','clock_interaction.rpt','methodology.rpt'))
    for name in sorted(paths):copy(name)
    for stage in ('simulation','hardware'):
        subprocess.run([sys.executable,'scripts/record_build_stage.py',stage,'--check'],cwd=ROOT,check=True)
    report=dict(status='PASS',time=datetime.datetime.now().astimezone().isoformat(),candidate=str(candidate),
        backup=str(backup),scope='Byte-identical import of independently completed builds; original log paths retained',files=transfer)
    (ROOT/'reports/phase3_candidate_import.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PHASE3_CANDIDATE_IMPORT_PASS')


if __name__=='__main__':main()
