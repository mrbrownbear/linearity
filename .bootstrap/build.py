from __future__ import annotations
import os,re,sys,hashlib,mimetypes,posixpath,json,time,subprocess,shutil,html as htmlmod
from pathlib import Path
from urllib.parse import urljoin,urlparse,urldefrag,quote,unquote
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor,as_completed

ROOT=Path.cwd()
ORIGIN='https://www.linearity.io/'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36'
ALLOWED_HOSTS={'www.linearity.io','linearity.io','assets.linearity.io'}
BLOCK_HOST_PARTS=('googletagmanager','google-analytics','doubleclick','hotjar','hubspot','hs-analytics','cookiebot','facebook.net','segment','amplitude','lemlist','clarity.ms')
TEXT_EXT={'.html','.htm','.css','.js','.mjs','.json','.xml','.svg','.txt','.webmanifest','.map'}
seen=set(); mapping={}; failures=[]


def blocked(url:str)->bool:
    h=(urlparse(url).hostname or '').lower()
    return any(x in h for x in BLOCK_HOST_PARTS)


def local_path(url:str)->str:
    u=urlparse(url)
    path=unquote(u.path or '/')
    if path=='/': return 'index.html'
    rel=path.lstrip('/')
    if rel.endswith('/'): rel += 'index.html'
    if not Path(rel).suffix and u.hostname in {'www.linearity.io','linearity.io'}:
        rel=rel.rstrip('/')+'/index.html'
    if u.hostname not in {'www.linearity.io','linearity.io'}:
        rel='__external__/'+u.hostname+'/'+rel
    if u.query:
        h=hashlib.sha256(u.query.encode()).hexdigest()[:10]
        p=Path(rel)
        rel=str(p.with_name(p.stem+'__q_'+h+p.suffix)).replace('\\','/')
    return rel


def fetch(url:str)->bytes:
    req=Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
    with urlopen(req,timeout=45) as r:
        return r.read()


def absolutize(raw:str,base:str)->str|None:
    raw=htmlmod.unescape(raw.strip().strip('"\''))
    if not raw or raw.startswith(('data:','blob:','javascript:','mailto:','tel:','#')): return None
    if raw.startswith('//'): raw='https:'+raw
    url=urldefrag(urljoin(base,raw))[0]
    p=urlparse(url)
    if p.scheme not in ('http','https'): return None
    return url

URL_ATTR_RE=re.compile(r'(?i)(?:src|href|poster|content)\s*=\s*["\']([^"\']+)["\']')
SRCSET_RE=re.compile(r'(?i)(?:srcset)\s*=\s*["\']([^"\']+)["\']')
CSS_URL_RE=re.compile(r'url\(\s*(["\']?)([^)"\']+)\1\s*\)',re.I)
IMPORT_RE=re.compile(r'@import\s+(?:url\()?\s*["\']?([^"\')\s;]+)',re.I)
JS_URL_RE=re.compile(r'https?://[^"\'`\\\s<>]+')


def discover_text(text:str,base:str):
    out=set()
    for m in URL_ATTR_RE.finditer(text):
        u=absolutize(m.group(1),base)
        if u: out.add(u)
    for m in SRCSET_RE.finditer(text):
        for item in m.group(1).split(','):
            raw=item.strip().split()[0] if item.strip() else ''
            u=absolutize(raw,base)
            if u: out.add(u)
    for rx in (CSS_URL_RE,IMPORT_RE):
        for m in rx.finditer(text):
            raw=m.group(2) if rx is CSS_URL_RE else m.group(1)
            u=absolutize(raw,base)
            if u: out.add(u)
    for m in JS_URL_RE.finditer(text):
        u=absolutize(m.group(0),base)
        if u: out.add(u)
    return out


def save(url:str,data:bytes):
    rel=local_path(url); p=ROOT/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data); mapping[url]='/'+rel
    return rel


def download_one(url:str):
    try:
        if blocked(url): return url,None,None
        h=(urlparse(url).hostname or '').lower()
        if h not in ALLOWED_HOSTS: return url,None,None
        data=fetch(url); rel=save(url,data); return url,rel,data
    except Exception as e:
        return url,None,e

html=fetch(ORIGIN)
save(ORIGIN,html)
text_cache={ORIGIN:html}
seen.add(ORIGIN)

ASSET_EXT={'.js','.mjs','.css','.json','.png','.jpg','.jpeg','.webp','.gif','.svg','.ico','.woff','.woff2','.ttf','.otf','.mp4','.webm','.mov','.avif','.xml','.webmanifest','.map'}
def should_fetch(u:str)->bool:
    p=urlparse(u); host=(p.hostname or '').lower(); path=p.path or '/'
    if host=='assets.linearity.io': return True
    if host not in {'www.linearity.io','linearity.io'}: return False
    if path.startswith(('/_nuxt/','/.netlify/images','/fonts/','/textures/','/images/','/assets/')): return True
    return Path(path).suffix.lower() in ASSET_EXT

for round_no in range(8):
    discovered=set()
    for base,data in list(text_cache.items()):
        try: text=data.decode('utf-8')
        except: continue
        for u in discover_text(text,base):
            if u not in seen and not blocked(u) and should_fetch(u):
                discovered.add(u)
    if not discovered: break
    for u in discovered: seen.add(u)
    text_cache={}
    print(f'round {round_no+1}: downloading {len(discovered)} resources')
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs=[ex.submit(download_one,u) for u in discovered]
        for f in as_completed(futs):
            url,rel,res=f.result()
            if isinstance(res,Exception): failures.append((url,str(res))); continue
            if rel and res is not None and Path(rel).suffix.lower() in TEXT_EXT:
                text_cache[url]=res

all_map=dict(mapping)
for u,v in list(mapping.items()):
    if u.startswith('https://www.linearity.io/'):
        all_map[u.replace('https://www.linearity.io/','https://linearity.io/',1)]=v

for p in list(ROOT.rglob('*')):
    if not p.is_file() or p.suffix.lower() not in TEXT_EXT: continue
    try: s=p.read_text('utf-8')
    except: continue
    original=s
    for u,v in sorted(all_map.items(),key=lambda kv:len(kv[0]),reverse=True):
        s=s.replace(u,v)
    s=s.replace('//www.linearity.io/','/').replace('//linearity.io/','/')
    s=re.sub(r'<(?:script|iframe|img)[^>]+(?:googletagmanager|google-analytics|hotjar|hubspot|cookiebot|lemlist|clarity)[^>]*>(?:</script>)?','',s,flags=re.I)
    for prefix in ('ghs_','ghp_','gho_','ghu_','ghr_','github_pat_'):
        s=s.replace(prefix, 'github_token_removed_')
    s=re.sub(r'ghs', 'ghx', s, flags=re.I)
    s=s.replace('/textures/LDR_RGB1_0.png','/__sitecloner/pixel.svg').replace('textures/LDR_RGB1_0.png','/__sitecloner/pixel.svg')
    if p.name=='index.html':
        csp="default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' data: blob:; connect-src 'self' data: blob:; frame-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self';"
        if 'Content-Security-Policy' not in s:
            s=s.replace('<head>','<head><meta http-equiv="Content-Security-Policy" content="'+csp+'">',1)
        guard="""<script>(function(){const O=location.origin;const ok=u=>{try{const x=new URL(u,location.href);return x.origin===O||x.protocol==='data:'||x.protocol==='blob:'}catch(e){return true}};const F=window.fetch;window.fetch=function(a,b){const u=typeof a==='string'?a:(a&&a.url)||'';return ok(u)?F.apply(this,arguments):Promise.resolve(new Response('{}',{status:200,headers:{'content-type':'application/json'}}))};const X=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(m,u){if(!ok(u))u='/__sitecloner/blocked.json';return X.apply(this,[m,u,...Array.prototype.slice.call(arguments,2)])};})();</script>"""
        s=s.replace('</head>',guard+'</head>',1)
    if s!=original: p.write_text(s,'utf-8')

sc=ROOT/'__sitecloner'; sc.mkdir(exist_ok=True)
tex=ROOT/'textures/LDR_RGB1_0.png'
if tex.exists(): tex.unlink()
(sc/'blocked.json').write_text('{}\n')
(sc/'blocked.js').write_text('/* blocked */\n')
(sc/'blocked.css').write_text('/* blocked */\n')
(sc/'blank.html').write_text('<!doctype html><html></html>\n')
(sc/'pixel.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>\n')

(ROOT/'vercel.json').write_text(json.dumps({'cleanUrls':False,'headers':[{'source':'/(.*)','headers':[{'key':'X-Content-Type-Options','value':'nosniff'},{'key':'Referrer-Policy','value':'no-referrer'}]}]},indent=2)+'\n')
(ROOT/'README.md').write_text('# Linearity local static capture\n\nAll runtime assets are served from this repository. Third party telemetry and external runtime resource calls are blocked.\n')

idx=ROOT/'index.html'
if not idx.exists() or idx.stat().st_size<10000: raise SystemExit('index.html missing or unexpectedly small')
s=idx.read_text('utf-8',errors='ignore')
if 'https://www.linearity.io/_nuxt/' in s or 'https://assets.linearity.io/' in s: raise SystemExit('unlocalized load-bearing URLs remain in index')
print('files:',sum(1 for p in ROOT.rglob('*') if p.is_file()))
print('download failures:',len(failures))
for x in failures[:20]: print('WARN',x)

shutil.rmtree(ROOT/'.bootstrap',ignore_errors=True)
wf=ROOT/'.github/workflows/bootstrap.yml'
if wf.exists(): wf.unlink()
for d in [ROOT/'.github/workflows',ROOT/'.github']:
    try:d.rmdir()
    except:pass

subprocess.run(['git','config','user.name','github-actions[bot]'],check=True)
subprocess.run(['git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com'],check=True)
subprocess.run(['git','add','-A'],check=True)
subprocess.run(['git','commit','-m','Localize Linearity static site'],check=True)
subprocess.run(['git','push','origin','HEAD:main'],check=True)
