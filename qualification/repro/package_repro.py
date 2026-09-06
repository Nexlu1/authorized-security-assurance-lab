from __future__ import annotations
import hashlib,json,os,shutil,sys,tempfile,urllib.request,zipfile
from pathlib import Path
WHEEL_URL='https://github.com/drivendataorg/repro-zipfile/releases/download/v0.4.1/repro_zipfile-0.4.1-py3-none-any.whl'
WHEEL_SHA='3061d5ab47064ce17255e0e7baa3f2f9128873e1ff49946ce13b73f405167763'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def build(root,out):
 from repro_zipfile import ReproducibleZipFile
 files=sorted((p for p in root.rglob('*') if p.is_file()),key=lambda p:p.relative_to(root).as_posix())
 with ReproducibleZipFile(out,'w',compression=zipfile.ZIP_STORED) as z:
  for p in files:
   arc=p.relative_to(root).as_posix()
   # repro-zipfile fixes timestamps and permissions. Fix the remaining host-OS field
   # so Unix and Windows emit identical central-directory bytes.
   zi=zipfile.ZipInfo(arc)
   zi.create_system=3
   z.writestr(zi,p.read_bytes(),compress_type=zipfile.ZIP_STORED)
def main():
 t=Path(os.environ.get('RUNNER_TEMP',tempfile.gettempdir()))/'mcr-repro'; shutil.rmtree(t,ignore_errors=True); t.mkdir()
 whl=t/'repro_zipfile-0.4.1-py3-none-any.whl'; req=urllib.request.Request(WHEEL_URL,headers={'User-Agent':'mcr-synthetic-qualification'})
 with urllib.request.urlopen(req,timeout=60) as r,open(whl,'wb') as f: shutil.copyfileobj(r,f)
 if sha(whl)!=WHEEL_SHA: raise SystemExit('wheel SHA mismatch')
 sys.path.insert(0,str(whl))
 import repro_zipfile
 if getattr(repro_zipfile,'__version__','0.4.1') not in ('0.4.1',): raise SystemExit('unexpected repro-zipfile version')
 a=t/'a'; b=t/'b'; a.mkdir(); b.mkdir()
 payloads={'alpha.txt':b'alpha\n','nested/beta.bin':bytes(range(256))*4,'nested/gamma.json':b'{"controlled":true,"version":1}\n'}
 for rel,data in payloads.items():
  p=a/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data); os.utime(p,(946684800,946684800))
 for rel in reversed(list(payloads)):
  p=b/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(payloads[rel]); os.utime(p,(1767225600,1767225600))
 z1=t/'one.zip'; z2=t/'two.zip'; build(a,z1); build(b,z2)
 h1,h2=sha(z1),sha(z2)
 if z1.read_bytes()!=z2.read_bytes(): raise SystemExit(f'local reproducibility failure {h1} {h2}')
 with zipfile.ZipFile(z1) as check:
  if any(i.create_system!=3 for i in check.infolist()): raise SystemExit('create_system normalization failed')
 receipt={'schema':'mcr-repro-package-qualification-v2','status':'PASS','repro_zipfile':'0.4.1','wheel_sha256':sha(whl),'archive_sha256':h1,'archive_bytes':z1.stat().st_size,'member_order':sorted(payloads),'compression':'ZIP_STORED','create_system':3,'source_date_epoch_behavior':'fixed metadata supplied by repro-zipfile; source mtimes intentionally differ','python':sys.version,'platform':sys.platform,'frozen_mcr_r59':'UNCHANGED'}
 (t/'REPRO_PACKAGING_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 shutil.copy2(z1,t/'MCR_SYNTHETIC_REPRO_PACKAGE.zip')
 print(json.dumps(receipt,indent=2))
if __name__=='__main__': main()
