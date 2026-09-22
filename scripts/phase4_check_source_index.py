"""Prove that staged build sources preserve the exact tested working-tree bytes."""
import datetime
import hashlib
import json
import subprocess
from record_build_stage import ROOT,inputs,sha

def main():
    tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'))
    selected=set(inputs('simulation'))|set(inputs('hardware'))
    selected.update(('scripts/program_board.tcl','scripts/maintenance/sd_export.tcl',
                     'scripts/maintenance/run_sd_application.tcl','scripts/maintenance/sd_boot_writer.tcl'))
    selected.update(p.relative_to(ROOT).as_posix() for folder in ('firmware','host','config')
                    for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    result={}
    for name in sorted(selected&tracked):
        blob=subprocess.check_output(['git','show',':'+name],cwd=ROOT)
        digest=hashlib.sha256(blob).hexdigest()
        if sha(ROOT/name)!=digest:raise ValueError('Git index would alter tested source bytes: '+name)
        result[name]=digest
    required={p.relative_to(ROOT).as_posix() for folder in ('rtl','firmware','host','config')
              for p in (ROOT/folder).glob('*') if p.is_file()}
    if not required<=set(result):raise ValueError('Required source is not staged: '+str(required-set(result)))
    report=dict(status='PASS',checked_at=datetime.datetime.now().astimezone().isoformat(),
        scope='Git index blobs are byte-identical to tested source. Generated build inputs are delivered separately.',
        files=result,generated_inputs_not_in_git=sorted(selected-tracked))
    (ROOT/'reports/phase4_source_checkout_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PHASE4_SOURCE_INDEX_PASS',len(result))

if __name__=='__main__':main()
