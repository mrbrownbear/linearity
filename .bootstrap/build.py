from __future__ import annotations
from pathlib import Path
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit
import base64, hashlib, json, lzma, shutil, subprocess, time, re, os

ROOT = Path.cwd()
BOOT = ROOT / '.bootstrap'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36'

def restore_seed(prefix: str) -> bytes:
    parts = sorted(BOOT.glob(prefix + '*'))
    if not parts:
        raise SystemExit(f'missing seed: {prefix}')
    encoded = ''.join(p.read_text('ascii').strip() for p in parts)
    return lzma.decompress(base64.b64decode(encoded), format=lzma.FORMAT_XZ)

index_bytes = restore_seed('index.html.xz.b64.')
resources_bytes = restore_seed('resources.xz.b64.')
resources = json.loads(resources_bytes.decode('utf-8'))
print('manifest resources:', len(resources))

(ROOT / 'index.html').write_bytes(index_bytes)

def download(item):
    dest = ROOT / item['path']
    dest.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(4):
        try:
            req = Request(item['url'], headers={'User-Agent': UA, 'Accept': '*/*'})
            with urlopen(req, timeout=60) as r:
                data = r.read()
            if not data:
                raise RuntimeError('empty response')
            expected = item.get('sha256') or ''
            if expected:
                actual = hashlib.sha256(data).hexdigest()
                if actual != expected:
                    print('HASH_MISMATCH', item['path'])
            dest.write_bytes(data)
            return item['path'], len(data), None
        except Exception as e:
            last = e
            time.sleep(1.2 * (attempt + 1))
    return item['path'], 0, str(last)

failures = []
total = 0
with ThreadPoolExecutor(max_workers=10) as pool:
    futs = [pool.submit(download, x) for x in resources]
    for i, fut in enumerate(as_completed(futs), 1):
        path, n, err = fut.result()
        total += n
        if err:
            failures.append((path, err))
        if i % 100 == 0 or i == len(futs):
            print(f'{i}/{len(futs)} resources processed')

print('downloaded bytes:', total)
print('download failures:', len(failures))

# Missing noncritical captured resources become local stubs, never live fallbacks.
for path, err in failures:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    ext = p.suffix.lower()
    if ext in {'.js', '.mjs'}:
        p.write_text('/* unavailable captured script intentionally stubbed */\n', 'utf-8')
    elif ext == '.css':
        p.write_text('/* unavailable captured stylesheet intentionally stubbed */\n', 'utf-8')
    elif ext == '.json':
        p.write_text('{}\n', 'utf-8')
    elif ext == '.svg':
        p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>\n', 'utf-8')
    else:
        p.write_bytes(b'')

sitecloner = ROOT / '__sitecloner'
sitecloner.mkdir(exist_ok=True)
(sitecloner / 'blocked.js').write_text('/* external runtime request intentionally blocked */\n','utf-8')
(sitecloner / 'blocked.css').write_text('/* external stylesheet intentionally blocked */\n','utf-8')
(sitecloner / 'blocked.json').write_text('{}\n','utf-8')
(sitecloner / 'blank.html').write_text('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>\n','utf-8')
(sitecloner / 'pixel.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>\n','utf-8')

# Build a local-only runtime mapper from the exact capture manifest.
mapping = {}
for item in resources:
    url = item.get('url')
    path = item.get('path')
    if url and path:
        mapping[url] = '/' + path.lstrip('/')

runtime = """(() => {
const M = __MAP__;
const BLOCK='/__sitecloner/blocked.json';
function mapUrl(value){
  if(!value || typeof value!=='string') return value;
  if(value.startsWith('data:')||value.startsWith('blob:')||value.startsWith('#')) return value;
  try{
    const u=new URL(value,location.href);
    const exact=M[u.href];
    if(exact) return exact;
    const noHash=u.origin+u.pathname+u.search;
    if(M[noHash]) return M[noHash];
    if(u.origin===location.origin) return u.pathname+u.search+u.hash;
    return BLOCK;
  }catch(e){return value}
}
const nativeFetch=window.fetch;
window.fetch=function(input,init){
  const raw=typeof input==='string'?input:(input&&input.url)||'';
  const mapped=mapUrl(raw);
  if(mapped===BLOCK) return Promise.resolve(new Response('{}',{status:200,headers:{'content-type':'application/json'}}));
  if(typeof input==='string') return nativeFetch.call(this,mapped,init);
  try{return nativeFetch.call(this,new Request(mapped,input),init)}catch(e){return nativeFetch.call(this,mapped,init)}
};
const xo=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(method,url,...rest){return xo.call(this,method,mapUrl(url),...rest)};
const sa=Element.prototype.setAttribute;
Element.prototype.setAttribute=function(name,value){
  if(['src','href','poster','action'].includes(String(name).toLowerCase())) value=mapUrl(value);
  return sa.call(this,name,value);
};
window.__LOCAL_CAPTURE_MAP__=M;
})();"""
runtime = runtime.replace('__MAP__', json.dumps(mapping, separators=(',', ':')))
(sitecloner / 'runtime.js').write_text(runtime, 'utf-8')

# Ensure local runtime is present even if the original clone omitted it.
html = (ROOT / 'index.html').read_text('utf-8', errors='ignore')
if '/__sitecloner/runtime.js' not in html:
    html = html.replace('</head>', '<script src="/__sitecloner/runtime.js"></script></head>', 1)

# Strict local-only CSP. Navigation can remain internal but resource/network calls cannot leave origin.
csp = "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' data: blob:; connect-src 'self' data: blob:; frame-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self';"
if 'Content-Security-Policy' not in html:
    html = html.replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="' + csp + '">', 1)

# Strip tracking tags and any credential-like strings from public captured text.
html = re.sub(r'<(?:script|iframe|img)[^>]+(?:googletagmanager|google-analytics|hotjar|hubspot|cookiebot|lemlist|clarity)[^>]*>(?:</script>)?', '', html, flags=re.I)
(ROOT / 'index.html').write_text(html, 'utf-8')

TEXT_EXT={'.html','.htm','.css','.js','.mjs','.json','.xml','.svg','.txt','.webmanifest','.map'}
for p in ROOT.rglob('*'):
    if not p.is_file() or p.suffix.lower() not in TEXT_EXT or '.git' in p.parts:
        continue
    try:
        s=p.read_text('utf-8')
    except Exception:
        continue
    o=s
    s=re.sub(r'ghs_[A-Za-z0-9.\\-_]{20,}', 'github_credential_removed', s, flags=re.I)
    s=re.sub(r'github_pat_[A-Za-z0-9_\\-]{20,}', 'github_credential_removed', s, flags=re.I)
    if s!=o:
        p.write_text(s,'utf-8')

# Local fallbacks for references absent from the supplied capture.
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
    if s.exists():
        d.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(s,d)

(ROOT/'vercel.json').write_text(json.dumps({
  'cleanUrls': False,
  'headers': [{'source':'/(.*)','headers':[
    {'key':'X-Content-Type-Options','value':'nosniff'},
    {'key':'Referrer-Policy','value':'no-referrer'},
    {'key':'Permissions-Policy','value':'camera=(), microphone=(), geolocation=()'}
  ]}]
}, indent=2)+'\n','utf-8')
(ROOT/'README.md').write_text('# Linearity local static capture\n\nRestored from the supplied capture. Runtime assets are served locally from this repository and outbound resource calls are blocked.\n','utf-8')

# Validate the deployment root and local references.
idx=ROOT/'index.html'
if not idx.exists() or idx.stat().st_size < 10000:
    raise SystemExit('index.html missing or invalid')
check=idx.read_text('utf-8',errors='ignore')
for bad in ['https://www.linearity.io/_nuxt/','https://linearity.io/_nuxt/','https://assets.linearity.io/']:
    if bad in check:
        raise SystemExit('unlocalized load-bearing URL remains: '+bad)
print('site files before cleanup:',sum(1 for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.parts))

# Remove the one-time importer from the final tree.
shutil.rmtree(BOOT, ignore_errors=True)
wf=ROOT/'.github/workflows/bootstrap.yml'
if wf.exists(): wf.unlink()
for d in [ROOT/'.github/workflows',ROOT/'.github']:
    try:d.rmdir()
    except OSError:pass

subprocess.run(['git','config','user.name','github-actions[bot]'],check=True)
subprocess.run(['git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com'],check=True)
subprocess.run(['git','add','-A'],check=True)
subprocess.run(['git','commit','-m','Restore localised Linearity capture'],check=True)
subprocess.run(['git','push','origin','HEAD:main'],check=True)

# repaired seed trigger

# full manifest repaired trigger
