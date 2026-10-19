from pathlib import Path
import hashlib,json,zipfile,subprocess,gzip

ROOT=Path('D:/fft'); REPO=ROOT/'phase13_github_archive_20261019'
D=REPO/'archives/phase13-report-reproduction-20261019'; A=ROOT/'phase13_archive_assets_20261019'
def digest(f):
 h=hashlib.sha256()
 for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def sha(p):
 with p.open('rb') as f:return digest(f)
m=json.loads(gzip.decompress((D/'file-manifest.json.gz').read_bytes()))
groups={};count=0
for e in m['files']:
 name,rel=e['archived_as'].split(':',1)
 if name=='git':
  assert sha(REPO/rel)==e['sha256'],rel
  assert sha(Path(e['source']))==e['sha256'],e['source']
  count+=1
 else:groups.setdefault(name,{})[rel]=e
for name,files in groups.items():
 print('Verifying',name,len(files),flush=True)
 with zipfile.ZipFile(A/name) as z:
  assert set(z.namelist())==set(files)
  for rel,e in files.items():
   assert z.getinfo(rel).file_size==e['bytes'],rel
   with z.open(rel) as f:assert digest(f)==e['sha256'],rel
   count+=1
print('Checking sealed reproduction package',flush=True)
p=ROOT/'fft_phase13_reproduction_20261013/release/phase13_sd_verified'
for line in (p/'SHA256SUMS.txt').read_text().splitlines():
 expected,name=line.split(maxsplit=1)
 assert sha(p/name)==expected,name
for name in ['报告.docx','报告.pdf']:
 assert sha(ROOT/name)==sha(D/'report'/name)
for line in (A/'SHA256SUMS.txt').read_text().splitlines():
 expected,name=line.split(maxsplit=1)
 assert sha(A/name)==expected,name
result={'status':'PASS','files_verified':count,'zip_members_verified':sum(map(len,groups.values())),'final_reports_byte_identical':True,'sealed_reproduction_package_checksums':'PASS','archive_asset_checksums':'PASS','note':'Archive integrity verification only; no new simulation or board measurement was performed.'}
(D/'archive-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
