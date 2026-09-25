"""Import the independently qualified combined build, retaining the old release."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
from record_build_stage import ROOT, sha

SOURCES = (
    '.gitattributes',
    'constraints/cdc.xdc', 'firmware/echo.c', 'firmware/sd_main.c',
    'host/iq_client.py', 'host/monitor.py', 'host/build_rates.py', 'host/analyze_sd.py', 'rtl/analyzer_core.sv',
    'rtl/iq_peripheral.sv', 'rtl/result_builder.sv', 'rtl/spectrum_measure.sv',
    'rtl/iq_build_config.sv', 'config/build_profile.json',
    'scripts/record_build_stage.py', 'scripts/run.ps1', 'scripts/sim_builder.tcl',
    'scripts/analyze_latency.py', 'scripts/phase4_build_config.py',
    'scripts/phase4_identity.py', 'scripts/phase4_test_identity.py',
    'scripts/deploy_board.py', 'scripts/validate_board.py', 'scripts/validate_measurements.py',
    'scripts/package_release.py', 'scripts/package_validated.py', 'scripts/maintenance/validate_sd.py',
    'scripts/verify_cold_boot.py',
    'tests/tb_axi.sv', 'tests/tb_core.sv', 'tests/tb_spectrum_edges.sv', 'tests/test_detector_host.py',
    'tests/fft_reference.py', 'tests/make_phase2_specs.py', 'tests/generate_qualification_vectors.py', 'tests/check_core_results.py',
    'build/config/build_identity.json', 'build/config/generated_clocks.tcl')

def require(ok, message):
    if not ok:raise ValueError(message)

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--backup',type=Path,required=True);a=p.parse_args()
    candidate=a.candidate.resolve();backup=a.backup.resolve()
    require(candidate!=ROOT and candidate.is_dir(),'Use the isolated completed combined candidate')
    require(backup.is_relative_to(ROOT/'build') and not backup.exists(),'Use a new project-local backup')
    freeze=ROOT/'build/phase4_initial_freeze_20260922/manifest.json'
    require(freeze.is_file() and json.loads(freeze.read_text())['status']=='PASS','Initial experiments must be frozen first')
    dirty=subprocess.check_output(['git','diff','--name-only','--','rtl','host','firmware','tests','constraints'],cwd=ROOT,text=True)
    require(not dirty.strip(),'Primary implementation has unreviewed edits; refusing to overwrite')
    subprocess.run([sys.executable,'scripts/package_release.py','--check'],cwd=candidate,check=True)
    subprocess.run([sys.executable,'-c','from scripts.package_validated import check_board; check_board()'],
                   cwd=candidate,env=__import__('os').environ|{'PYTHONPATH':str(candidate/'scripts')},check=True)
    board=json.loads((candidate/'reports/current_board_validation.json').read_text())
    timing=json.loads((candidate/'reports/hardware_validation.json').read_text())
    require(board['status']=='PASS' and board['suite']=='full' and len(board['cases'])==36,'Combined board suite incomplete')
    require(board['hardware']['scan_lanes']==8 and board['maximum_analysis_us']<=178,'Combined performance gate failed')
    require(timing['setup_slack_ns']>=.10 and timing['hold_slack_ns']>=0,'Combined timing margin gate failed')
    manifests={stage:json.loads((candidate/'reports'/f'{stage}_provenance.json').read_text())
               for stage in ('simulation','hardware')}
    for manifest in manifests.values():
        for name,digest in manifest['inputs'].items():
            if name not in SOURCES:
                require((ROOT/name).is_file() and sha(ROOT/name)==digest,'Unapproved input difference: '+name)
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
        require(sha(destination)==sha(source),'Copy mismatch: '+name);transfer[name]=sha(source)
    for name in SOURCES:copy(name)
    board_path=(ROOT/'build/board').resolve();saved_board=(backup/'board_project').resolve()
    require(board_path.is_relative_to(ROOT) and saved_board.is_relative_to(ROOT) and not saved_board.exists(),'Unsafe board move')
    board_path.rename(saved_board)
    shutil.copytree(candidate/'build/board',board_path,copy_function=shutil.copy2)
    for name in ('iq_analyzer.bit','iq_analyzer.xsa','iq_udp.elf','iq_sd.elf','zynq_fsbl.elf'):
        copy('artifacts/'+name)
    paths={'reports/software_validation.json','build/vivado/iq_analyzer.sim/sim_1/behav/xsim/core_results.txt'}
    for stage,manifest in manifests.items():
        paths.add(f'reports/{stage}_provenance.json');paths.update(manifest['evidence'])
    paths.update('reports/'+name for name in ('utilization.rpt','clock_interaction.rpt','methodology.rpt'))
    for name in sorted(paths):copy(name)
    for stage in ('simulation','hardware'):
        subprocess.run([sys.executable,'scripts/record_build_stage.py',stage,'--check'],cwd=ROOT,check=True)
    report=dict(status='PASS',time=datetime.datetime.now().astimezone().isoformat(),candidate=str(candidate),backup=str(backup),
        scope='Byte-identical source/build import; primary tree requires its own new board/reference campaign',
        isolated_board=board,isolated_board_sha256=sha(candidate/'reports/current_board_validation.json'),files=transfer)
    (ROOT/'reports/phase4_candidate_import.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PHASE4_CANDIDATE_IMPORT_PASS')

if __name__=='__main__':main()
