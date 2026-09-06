import base64,hashlib,json,os,platform,shutil,subprocess,tempfile,urllib.request,zipfile
from pathlib import Path
DATA=("https://github.com/richardlehane/siegfried/releases/download/v1.11.6/data_1-11-6.zip","97921fd54db3e5e2b7646756dd3e47c34a19540b3f5d174370205c2df5cf3de7")
WIN=("https://github.com/richardlehane/siegfried/releases/download/v1.11.6/siegfried_1-11-6_win64.zip","ad5b571c2628e159e103ce7845c2b056724517162bcaa34161c5fb7473e16501")
LIN=("https://github.com/richardlehane/siegfried/releases/download/v1.11.6/siegfried_1-11-6_linux64_static.zip","033f40ea1e82e2cea3fcd5c408114a2d67d2e091560ee5959d2d17118734dd06")
def sha(p):
 h=hashlib.sha256();
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def dl(url,p,exp):
 req=urllib.request.Request(url,headers={'User-Agent':'mcr-synthetic-qualification'})
 with urllib.request.urlopen(req,timeout=60) as r,open(p,'wb') as f: shutil.copyfileobj(r,f)
 if sha(p)!=exp: raise SystemExit(f'hash mismatch {p}')
def unzip(src,dst):
 with zipfile.ZipFile(src) as z:
  if z.testzip(): raise SystemExit(f'bad zip {src}')
  for i in z.infolist():
   q=Path(i.filename)
   if q.is_absolute() or '..' in q.parts: raise SystemExit(f'unsafe member {i.filename}')
  z.extractall(dst)
def run(c):
 p=subprocess.run(c,text=True,capture_output=True,timeout=30); return p.returncode,p.stdout,p.stderr
root=Path(os.environ.get('RUNNER_TEMP',tempfile.gettempdir()))/'mcr-siegfried-qualification'; shutil.rmtree(root,ignore_errors=True); root.mkdir()
windows=os.name=='nt'; tool=WIN if windows else LIN
tz=root/'tool.zip'; dz=root/'data.zip'; td=root/'tool'; dd=root/'data'; td.mkdir(); dd.mkdir(); dl(*tool,tz) if False else None
dl(tool[0],tz,tool[1]); dl(DATA[0],dz,DATA[1]); unzip(tz,td); unzip(dz,dd)
exe=list(td.rglob('sf.exe' if windows else 'sf')); sig=list(dd.rglob('default.sig'))
if len(exe)!=1 or len(sig)!=1: raise SystemExit(f'expected one sf and one default.sig: {exe} {sig}')
exe,sig=exe[0],sig[0]
if not windows: exe.chmod(exe.stat().st_mode|0o111)
gif=root/'synthetic.gif'; gif.write_bytes(base64.b64decode('R0lGODdhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='))
home=str(sig.parent)
vr=run([str(exe),'-home',home,'-sig',sig.name,'-version']); ir=run([str(exe),'-home',home,'-sig',sig.name,'-json',str(gif)])
if vr[0]!=0 or ir[0]!=0 or 'fmt/' not in ir[1]: raise SystemExit(f'qualification failure version={vr} identify={ir}')
r={'schema':'mcr-siegfried-pronom-qualification-v1','status':'PASS','release':'v1.11.6','platform':platform.platform(),'tool_asset_sha256':sha(tz),'tool_executable_sha256':sha(exe),'tool_executable_bytes':exe.stat().st_size,'data_asset_sha256':sha(dz),'default_sig_sha256':sha(sig),'default_sig_bytes':sig.stat().st_size,'default_sig_relative_path':sig.relative_to(dd).as_posix(),'version_stdout':vr[1],'identify_stdout':ir[1],'synthetic_gif_sha256':sha(gif),'frozen_mcr_r59':'UNCHANGED'}
(root/'SIEGFRIED_PRONOM_QUALIFICATION_RECEIPT.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','default_sig_sha256':r['default_sig_sha256'],'executable_sha256':r['tool_executable_sha256']},indent=2))
