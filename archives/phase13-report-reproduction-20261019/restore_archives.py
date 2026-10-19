from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
m=json.loads((ROOT/'split-manifest.json').read_text('utf-8'))
for a in m['archives']:
 out=ROOT/a['name']
 if out.exists() and sha(out)==a['sha256']:
  print('Already verified:',out.name);continue
 for p in a['parts']:
  src=ROOT/p['name']
  assert src.stat().st_size==p['bytes'] and sha(src)==p['sha256'],str(src)
 temp=out.with_name(out.name+'.assembling')
 with temp.open('wb') as w:
  for p in a['parts']:
   with (ROOT/p['name']).open('rb') as f:
    for b in iter(lambda:f.read(1024*1024),b''):w.write(b)
 assert temp.stat().st_size==a['bytes'] and sha(temp)==a['sha256'],out.name
 temp.replace(out)
 print('Restored and verified:',out.name)
print('PASS: both original ZIP archives restored byte-for-byte. Part files retained.')
