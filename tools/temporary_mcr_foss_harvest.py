#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, os, pathlib, re, shutil, subprocess, sys, time, urllib.parse, urllib.request, zipfile
from datetime import datetime, timezone

ROOT = pathlib.Path('harvest-work')
PAYLOAD = ROOT / 'MCR_GITHUB_FOSS_ACTIVE_STACK_HARVEST_R1_2026-09-04'
OUT_DIR = pathlib.Path('harvest-output')
OUT_ZIP = OUT_DIR / 'MCR_GITHUB_FOSS_ACTIVE_STACK_HARVEST_R1_2026-09-04.zip'
MANIFEST_PATH = pathlib.Path('controls/mcr_foss_active_stack_manifest.json')
TOKEN = os.environ.get('GH_TOKEN','')
API = 'https://api.github.com'
UA = 'mcr-foss-harvest/1.0'
FIXED_ZIP_TIME=(2026,9,4,0,0,0)
failures=[]
source_records=[]
binary_records=[]
license_records=[]

def now(): return datetime.now(timezone.utc).isoformat()
def sha256_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def safe_name(s): return re.sub(r'[^A-Za-z0-9._-]+','_',s).strip('_')
def request(url, accept='application/vnd.github+json'):
    headers={'User-Agent':UA,'Accept':accept,'X-GitHub-Api-Version':'2022-11-28'}
    if TOKEN: headers['Authorization']='Bearer '+TOKEN
    return urllib.request.Request(url, headers=headers)
def api_json(path):
    with urllib.request.urlopen(request(API+path), timeout=90) as r:
        return json.load(r)
def download(url, dest, retries=4):
    dest.parent.mkdir(parents=True,exist_ok=True)
    last=None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request(url,'application/octet-stream'), timeout=180) as r, open(dest,'wb') as f:
                shutil.copyfileobj(r,f,1024*1024)
            return
        except Exception as e:
            last=e
            if dest.exists(): dest.unlink()
            time.sleep(2**attempt)
    raise last

def resolve_ref(repo, kind, ref):
    if kind=='commit':
        obj=api_json(f'/repos/{repo}/commits/{urllib.parse.quote(ref,safe="")}')
        sha=obj['sha']
        if sha.lower()!=ref.lower(): raise RuntimeError(f'commit resolution mismatch {ref} -> {sha}')
        return sha
    if kind!='tag': raise RuntimeError('unknown ref kind '+kind)
    obj=api_json(f'/repos/{repo}/git/ref/tags/{urllib.parse.quote(ref,safe="")}')['object']
    seen=set()
    while obj['type']=='tag':
        if obj['sha'] in seen: raise RuntimeError('annotated tag cycle')
        seen.add(obj['sha'])
        obj=api_json(f'/repos/{repo}/git/tags/{obj["sha"]}')['object']
    if obj['type']!='commit': raise RuntimeError(f'tag resolves to {obj["type"]}')
    return obj['sha']

LICENSE_RE=re.compile(r'^(?:license|licence|copying|notice|copyright)(?:[-._].*)?$',re.I)
def extract_licenses(component, src_zip):
    out=PAYLOAD/'licenses'/safe_name(component)
    found=[]
    with zipfile.ZipFile(src_zip) as z:
        bad=z.testzip()
        if bad: raise RuntimeError('source zip CRC failure: '+bad)
        for info in sorted(z.infolist(),key=lambda x:x.filename.lower()):
            if info.is_dir() or info.file_size>2_000_000: continue
            parts=pathlib.PurePosixPath(info.filename).parts
            rel=parts[1:] if len(parts)>1 else parts
            if not rel or len(rel)>4: continue
            in_licence_dir = any(part.lower() in {'licenses', 'licences', 'build_licenses'} for part in rel[:-1])
            if not LICENSE_RE.match(rel[-1]) and not in_licence_dir: continue
            data=z.read(info)
            out.mkdir(parents=True,exist_ok=True)
            dest=out/safe_name('__'.join(rel))
            dest.write_bytes(data)
            rec={'component':component,'source_member':info.filename,'file':str(dest.relative_to(PAYLOAD)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            license_records.append(rec); found.append(rec)
    return found

def harvest_source(item):
    component=item['component']; repo=item['repo']; required=bool(item.get('required'))
    rec={**item,'status':'STARTED','started_utc':now()}
    try:
        sha=resolve_ref(repo,item['ref_kind'],item['ref'])
        dest=PAYLOAD/'sources'/f'{safe_name(component)}__{safe_name(repo)}__{sha}.zip'
        download(f'https://codeload.github.com/{repo}/zip/{sha}',dest)
        licenses=extract_licenses(component,dest)
        if not licenses: raise RuntimeError('no root/near-root licence or notice file found')
        rec.update(status='DOWNLOADED_AND_HASHED',resolved_commit=sha,file=str(dest.relative_to(PAYLOAD)),bytes=dest.stat().st_size,sha256=sha256_file(dest),licence_files=[x['file'] for x in licenses],completed_utc=now())
    except Exception as e:
        rec.update(status='FAILED',error=f'{type(e).__name__}: {e}',completed_utc=now())
        failures.append({'kind':'source','component':component,'repo':repo,'required':required,'error':rec['error']})
    source_records.append(rec)

def harvest_binary(item):
    component=item['component']; repo=item['repo']; required=bool(item.get('required'))
    rec={**item,'status':'STARTED','started_utc':now()}
    try:
        release=api_json(f'/repos/{repo}/releases/tags/{urllib.parse.quote(item["tag"],safe="")}')
        rx=re.compile(item['asset_regex'])
        matches=[a for a in release.get('assets',[]) if rx.match(a['name'])]
        if len(matches)!=1:
            raise RuntimeError(f'asset regex matched {len(matches)}; release assets={[a["name"] for a in release.get("assets",[])]}')
        asset=matches[0]
        dest=PAYLOAD/'windows-portable'/safe_name(component)/asset['name']
        download(asset['browser_download_url'],dest)
        actual=sha256_file(dest)
        api_digest=(asset.get('digest') or '').removeprefix('sha256:') or None
        expected=item.get('expected_sha256')
        if api_digest and actual.lower()!=api_digest.lower(): raise RuntimeError(f'GitHub digest mismatch {actual} != {api_digest}')
        if expected and actual.lower()!=expected.lower(): raise RuntimeError(f'controlled expected digest mismatch {actual} != {expected}')
        inner=[]
        if zipfile.is_zipfile(dest):
            with zipfile.ZipFile(dest) as z:
                bad=z.testzip()
                if bad: raise RuntimeError('release ZIP CRC failure: '+bad)
                for zi in z.infolist():
                    n=zi.filename.lower()
                    if n.endswith(('.sig','.sig.json','.json','.xml')) or 'pronom' in n or n.endswith('default.sig'):
                        if zi.file_size<=100_000_000:
                            data=z.read(zi)
                            inner.append({'member':zi.filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        rec.update(status='DOWNLOADED_AND_VERIFIED',release_id=release.get('id'),asset_id=asset.get('id'),asset_name=asset['name'],file=str(dest.relative_to(PAYLOAD)),bytes=dest.stat().st_size,sha256=actual,github_digest=api_digest,inner_signature_candidates=inner,completed_utc=now())
    except Exception as e:
        rec.update(status='FAILED',error=f'{type(e).__name__}: {e}',completed_utc=now())
        failures.append({'kind':'windows_asset','component':component,'repo':repo,'required':required,'error':rec['error']})
    binary_records.append(rec)

def cargo_toml(deps):
    lines=['[package]','name = "mcr-vendor-lock"','version = "0.0.0"','edition = "2024"','rust-version = "1.88"','publish = false','','[dependencies]']
    for name,val in deps.items():
        if isinstance(val,str): lines.append(f'{name} = "{val}"')
        else:
            features=', '.join(json.dumps(x) for x in val.get('features',[]))
            lines.append(f'{name} = {{ version = {json.dumps(val["version"])}, features = [{features}] }}')
    return '\n'.join(lines)+'\n'

def run_cargo_vendor(cfg):
    rec={'status':'STARTED','started_utc':now(),'rust_toolchain':cfg['rust_toolchain']}
    root=PAYLOAD/'cargo-vendor'
    try:
        (root/'src').mkdir(parents=True,exist_ok=True)
        (root/'src/lib.rs').write_text('// Dependency-lock-only synthetic crate.\n',encoding='utf-8')
        (root/'Cargo.toml').write_text(cargo_toml(cfg['manifest']),encoding='utf-8')
        subprocess.run(['rustup','toolchain','install',cfg['rust_toolchain'],'--profile','minimal'],check=True,timeout=900)
        cargo=f'+{cfg["rust_toolchain"]}'
        subprocess.run(['cargo',cargo,'generate-lockfile','--manifest-path',str(root/'Cargo.toml')],check=True,timeout=600)
        vendor=root/'vendor'; vendor.mkdir(exist_ok=True)
        p=subprocess.run(['cargo',cargo,'vendor','--locked','--versioned-dirs','--manifest-path',str(root/'Cargo.toml'),str(vendor)],check=True,timeout=1800,capture_output=True,text=True)
        (root/'.cargo').mkdir(exist_ok=True)
        (root/'.cargo/config.toml').write_text(p.stdout,encoding='utf-8')
        subprocess.run(['cargo',cargo,'metadata','--locked','--offline','--manifest-path',str(root/'Cargo.toml'),'--format-version','1'],check=True,timeout=600,stdout=subprocess.DEVNULL)
        count=sum(1 for pth in vendor.rglob('*') if pth.is_file())
        size=sum(pth.stat().st_size for pth in vendor.rglob('*') if pth.is_file())
        rec.update(status='DOWNLOADED_LOCKED_AND_OFFLINE_METADATA_VERIFIED',cargo_lock_sha256=sha256_file(root/'Cargo.lock'),vendor_files=count,vendor_bytes=size,completed_utc=now())
    except Exception as e:
        rec.update(status='FAILED',error=f'{type(e).__name__}: {e}',completed_utc=now())
        failures.append({'kind':'cargo_vendor','component':'mcr-ingest exact Rust dependency graph','required':bool(cfg.get('required')),'error':rec['error']})
    return rec

def write_controls(plan,cargo_record):
    control=PAYLOAD/'CONTROL'; control.mkdir(parents=True,exist_ok=True)
    (control/'ACTIVE_COMPONENT_LOCK.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    (control/'OPTIONAL_HOLD_REGISTER.json').write_text(json.dumps(plan['optional_hold_not_downloaded_as_active'],indent=2),encoding='utf-8')
    result={'schema':'mcr-github-foss-active-stack-harvest-result-v1','generated_utc':now(),'source_count_requested':len(plan['sources']),'source_count_downloaded':sum(r['status']=='DOWNLOADED_AND_HASHED' for r in source_records),'windows_asset_count_requested':len(plan['windows_release_assets']),'windows_asset_count_downloaded':sum(r['status']=='DOWNLOADED_AND_VERIFIED' for r in binary_records),'cargo_vendor':cargo_record,'sources':source_records,'windows_assets':binary_records,'licence_files':license_records,'failures':failures,'required_failures':[f for f in failures if f['required']]}
    (control/'HARVEST_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    with open(control/'SOURCE_REGISTER.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['component','repo','requested_ref','resolved_commit','expected_license','use','status','bytes','sha256','error']);w.writeheader()
        for r in source_records:w.writerow({'component':r['component'],'repo':r['repo'],'requested_ref':r['ref'],'resolved_commit':r.get('resolved_commit',''),'expected_license':r['expected_license'],'use':r['use'],'status':r['status'],'bytes':r.get('bytes',''),'sha256':r.get('sha256',''),'error':r.get('error','')})
    with open(control/'WINDOWS_ASSET_REGISTER.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['component','repo','tag','asset_name','status','bytes','sha256','github_digest','error']);w.writeheader()
        for r in binary_records:w.writerow({k:r.get(k,'') for k in w.fieldnames})
    readme=f"""# MCR GitHub/FOSS Active Stack Harvest R1\n\nGenerated: {result['generated_utc']}\n\nThis package contains exact public GitHub source snapshots, extracted licence/notice files, selected hash-verified Windows portable release assets, and a Cargo-vendored copy of the exact Rust dependency graph needed by the active MCR future-tooling lane.\n\nIt contains no real MCR evidence, personal data, credentials or frozen R59 bytes.\n\n- Requested source repositories: {result['source_count_requested']}\n- Downloaded and hashed source repositories: {result['source_count_downloaded']}\n- Requested Windows assets: {result['windows_asset_count_requested']}\n- Downloaded and verified Windows assets: {result['windows_asset_count_downloaded']}\n- Required failures: {len(result['required_failures'])}\n- Optional/non-required failures: {len(failures)-len(result['required_failures'])}\n- Cargo vendor status: {cargo_record['status']}\n\nA downloaded source snapshot is not automatically incorporated. `use` and licence classifications in the registers control whether code is wrapped, linked as a dependency, adapted with attribution, held, or kept external.\n"""
    (control/'README.md').write_text(readme,encoding='utf-8')
    (control/'EXECUTION_RECEIPT.json').write_text(json.dumps({'generated_utc':now(),'github_repository':os.environ.get('GITHUB_REPOSITORY'),'github_ref':os.environ.get('GITHUB_REF'),'github_sha':os.environ.get('GITHUB_SHA'),'github_run_id':os.environ.get('GITHUB_RUN_ID'),'runner_os':os.environ.get('RUNNER_OS'),'runner_arch':os.environ.get('RUNNER_ARCH')},indent=2),encoding='utf-8')
    return result

def build_hash_manifest():
    rows=[]
    for p in sorted(PAYLOAD.rglob('*'),key=lambda x:x.as_posix().lower()):
        if p.is_file() and p.name!='SHA256SUMS.txt': rows.append((sha256_file(p),p.relative_to(PAYLOAD).as_posix(),p.stat().st_size))
    c=PAYLOAD/'CONTROL'
    (c/'SHA256SUMS.txt').write_text(''.join(f'{h}  {name}\n' for h,name,_ in rows),encoding='utf-8')
    (c/'FILE_MANIFEST.json').write_text(json.dumps([{'path':name,'bytes':size,'sha256':h} for h,name,size in rows],indent=2),encoding='utf-8')

def deterministic_zip():
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    if OUT_ZIP.exists(): OUT_ZIP.unlink()
    with zipfile.ZipFile(OUT_ZIP,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
        for p in sorted(PAYLOAD.rglob('*'),key=lambda x:x.as_posix().lower()):
            if not p.is_file(): continue
            arc=f'{PAYLOAD.name}/{p.relative_to(PAYLOAD).as_posix()}'
            zi=zipfile.ZipInfo(arc,FIXED_ZIP_TIME); zi.compress_type=zipfile.ZIP_STORED; zi.external_attr=0o100644<<16
            with open(p,'rb') as f: z.writestr(zi,f.read())
    with zipfile.ZipFile(OUT_ZIP) as z:
        bad=z.testzip()
        if bad: raise RuntimeError('outer zip CRC failure '+bad)
    (OUT_DIR/'OUTER_SHA256.txt').write_text(f'{sha256_file(OUT_ZIP)}  {OUT_ZIP.name}\n',encoding='utf-8')


def main():
    if ROOT.exists(): shutil.rmtree(ROOT)
    PAYLOAD.mkdir(parents=True)
    plan=json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    for i,item in enumerate(plan['sources'],1):
        print(f'[source {i}/{len(plan["sources"])}] {item["repo"]}',flush=True); harvest_source(item)
    for i,item in enumerate(plan['windows_release_assets'],1):
        print(f'[asset {i}/{len(plan["windows_release_assets"])}] {item["repo"]} {item["component"]}',flush=True); harvest_binary(item)
    print('[cargo] vendoring exact Rust dependency graph',flush=True)
    cargo_record=run_cargo_vendor(plan['cargo_vendor'])
    result=write_controls(plan,cargo_record)
    build_hash_manifest(); deterministic_zip()
    print(json.dumps({'outer_zip':str(OUT_ZIP),'outer_sha256':sha256_file(OUT_ZIP),'bytes':OUT_ZIP.stat().st_size,'required_failures':len(result['required_failures']),'total_failures':len(failures)},indent=2))

if __name__=='__main__': main()
