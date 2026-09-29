"""Preserve isolated candidate source and basic-board evidence for the decision record."""
import hashlib
import json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/phase4_candidate_evidence_20260922'
def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
for label,tree in (('scan',Path('D:/fft/iq_phase4_scan')),('clock125',Path('D:/fft/iq_phase4_clock125'))):
    sources=[p for folder in ('rtl','constraints','scripts','tests','host','firmware','vendor/boards','data')
             for p in (tree/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    sources += [p for p in (tree/'build/logs').glob('*') if p.is_file()]
    if label=='scan':
        sources += [p for p in (tree/'captures/phase4_scan_20260922').rglob('*') if p.is_file()
                    and p.name not in ('frequency.json','frequency.csv','burst.json','burst.csv')]
    else:
        sources += [tree/'EXPERIMENT_SCOPE.md']
        sources += [p for p in (tree/'build/clock_request150_failed').rglob('*') if p.is_file()]
    destination=BASE/label/'source_and_evidence.zip'
    manifest={p.relative_to(tree).as_posix():sha(p) for p in sources}
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for p in sources:z.write(p,p.relative_to(tree))
        z.writestr('archive_manifest.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(destination) as z:assert z.testzip() is None
    (BASE/label/'archive_check.json').write_text(json.dumps(dict(status='PASS',files=len(manifest),
        sha256=sha(destination),source_tree=str(tree),scope='Isolated experiment; not the final release'),indent=2))
    print('CANDIDATE_ARCHIVED',label,len(manifest),flush=True)
