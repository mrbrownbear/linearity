from __future__ import annotations
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64, hashlib, json, lzma, os, shutil, subprocess, sys, time

ROOT = Path.cwd()
BOOT = ROOT / '.bootstrap'
resources = json.loads((BOOT / 'resources.json').read_text('utf-8'))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36'

def download(item):
    dest = ROOT / item['path']
    dest.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(4):
        try:
            req = Request(item['url'], headers={'User-Agent': UA, 'Accept': '*/*'})
            with urlopen(req, timeout=60) as r:
                data = r.read()
                if getattr(r, 'status', 200) >= 400:
                    raise RuntimeError(f"HTTP {r.status}")
            if not data:
                raise RuntimeError('empty response')
            dest.write_bytes(data)
            expected = item.get('sha256') or ''
            if expected:
                actual = hashlib.sha256(data).hexdigest()
                if actual != expected:
                    print(f"HASH WARNING {item['path']} expected {expected} got {actual}")
            return item['path'], len(data), None
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    return item['path'], 0, str(last)

print(f'Downloading {len(resources)} captured resources')
failures=[]
bytes_total=0
with ThreadPoolExecutor(max_workers=8) as pool:
    futs=[pool.submit(download,x) for x in resources]
    for i,f in enumerate(as_completed(futs),1):
        path,n,err=f.result()
        bytes_total += n
        if err: failures.append((path,err))
        if i % 75 == 0 or i == len(futs): print(f'{i}/{len(futs)} resources complete')
if failures:
    print('Download failures:', file=sys.stderr)
    for p,e in failures: print(f'  {p}: {e}', file=sys.stderr)
    raise SystemExit(2)
print(f'Downloaded {bytes_total} bytes')

# Restore the exact patched homepage and local runtime prepared from the supplied capture.
for seed, out in [('index.html.xz.b64','index.html'),('runtime.js.xz.b64','__sitecloner/runtime.js')]:
    raw=base64.b64decode((BOOT/seed).read_text('ascii'))
    data=lzma.decompress(raw,format=lzma.FORMAT_XZ)
    p=ROOT/out; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)

# Local blockers and deployment policy.
sitecloner=ROOT/'__sitecloner'; sitecloner.mkdir(exist_ok=True)
(sitecloner/'blocked.js').write_text('/* external runtime request intentionally blocked */\n','utf-8')
(sitecloner/'blocked.css').write_text('/* external stylesheet intentionally blocked */\n','utf-8')
(sitecloner/'blocked.json').write_text('{}\n','utf-8')
(sitecloner/'blank.html').write_text('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>\n','utf-8')
(sitecloner/'pixel.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>\n','utf-8')
(ROOT/'vercel.json').write_text(json.dumps({
  'cleanUrls': False,
  'headers': [{'source':'/(.*)','headers':[
    {'key':'X-Content-Type-Options','value':'nosniff'},
    {'key':'Referrer-Policy','value':'no-referrer'},
    {'key':'Permissions-Policy','value':'camera=(), microphone=(), geolocation=()'}
  ]}]
},indent=2)+'\n','utf-8')
(ROOT/'README.md').write_text(
'''# Linearity static localised capture\n\nThis repository contains a self contained static capture. Runtime assets are served from this repository. Third party telemetry and the original live site resource calls are blocked.\n\nDeploy as a static site with the repository root as the output directory.\n''','utf-8')

# Missing references in the supplied capture are satisfied from equivalent captured local files.
copy_pairs={
  'apple-touch-icon.png':'android-chrome-192x192__q_f67bbdbffc.png',
  'favicon-16x16.png':'favicon-32x32__q_f67bbdbffc.png',
  'favicon-32x32.png':'favicon-32x32__q_f67bbdbffc.png',
  'fonts/FFF-AcidGrotesk-Bold.woff2':'fonts/FFF-AcidGrotesk-Medium.woff2',
  'fonts/MonumentGrotesk-Semi-Mono.woff2':'fonts/Inter-Medium.woff2',
  'fonts/ABCMonumentGroteskMono-Bold-Trial.woff2':'fonts/FFF-AcidGrotesk-Medium.woff2',
}
for dst,src in copy_pairs.items():
    s=ROOT/src; d=ROOT/dst
    if not s.is_file(): raise SystemExit(f'Missing fallback source: {src}')
    d.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(s,d)

# Final integrity checks.
expected_files=704
control_roots={'.bootstrap','.github','.git'}
site_files=[p for p in ROOT.rglob('*') if p.is_file() and not any(part in control_roots for part in p.parts)]
if len(site_files) != expected_files:
    print(f'Expected {expected_files} site files, found {len(site_files)}', file=sys.stderr)
    raise SystemExit(3)
for p in [ROOT/'index.html', ROOT/'__sitecloner/runtime.js', ROOT/'vercel.json']:
    if not p.is_file() or p.stat().st_size == 0: raise SystemExit(f'Missing critical file: {p}')
subprocess.run(['node','--check',str(ROOT/'__sitecloner/runtime.js')],check=True)
json.loads((ROOT/'vercel.json').read_text('utf-8'))
html=(ROOT/'index.html').read_text('utf-8',errors='ignore')
if '/.netlify/images?' in html or '/_payload.json?' in html:
    raise SystemExit('Unresolved Netlify or payload query route remains in index.html')
for bad in ['googletagmanager.com/ns.html','app.lemlist.com/api/visitors/tracking']:
    if bad in html: raise SystemExit(f'External tracker remains in index: {bad}')
if 'connect-src \'self\' data: blob:' not in html:
    raise SystemExit('Strict local CSP missing')
print(f'Integrity checks passed with {len(site_files)} site files')

# Remove one time bootstrap controls so the final repository is the deployable site only.
shutil.rmtree(BOOT,ignore_errors=True)
wf=ROOT/'.github/workflows/bootstrap.yml'
if wf.exists(): wf.unlink()
for d in [ROOT/'.github/workflows',ROOT/'.github']:
    try:d.rmdir()
    except OSError:pass
