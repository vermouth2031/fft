"""Freeze initial Phase 4 sources/reports without duplicating immutable raw captures."""
import datetime
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'build/phase4_initial_freeze_20260922'
out.mkdir(exist_ok=False)
def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream, 'sha256').hexdigest()
files = [p for folder in ('rtl', 'host', 'tests', 'firmware', 'scripts', 'constraints', 'reports', 'data', 'vendor')
         for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
files += list(ROOT.glob('*.md'))
with zipfile.ZipFile(out/'source_and_reports.zip', 'x', zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,p.relative_to(ROOT))
with zipfile.ZipFile(out/'source_and_reports.zip') as z:assert z.testzip() is None
evidence = {}
for folder in ('build/phase4_ofdm_20260922', 'build/phase4_ofdm_widest_20260922',
               'build/phase4_frequency_20260922_v2', 'build/phase4_noise_20260922',
               'captures/phase4_ofdm_20260922', 'captures/phase4_ofdm_widest_20260922',
               'captures/phase4_noise_20260922', 'captures/phase4_demo_20260922_v2'):
    for p in (ROOT/folder).rglob('*'):
        if p.is_file():evidence[p.relative_to(ROOT).as_posix()] = sha(p)
report = dict(status='PASS',created_at=datetime.datetime.now().astimezone().isoformat(),
    scope='Historical Phase 4 experiments on the Phase 3 100MSPS four-lane hardware. '
          'Frozen source archive supplies the original bindings; raw evidence remains at listed paths.',
    source_archive_sha256=sha(out/'source_and_reports.zip'),
    source_files={p.relative_to(ROOT).as_posix():sha(p) for p in files},evidence=evidence)
(out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('INITIAL_PHASE4_FROZEN', len(evidence), report['source_archive_sha256'])
