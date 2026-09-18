from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import base64, json, lzma, re, subprocess

ROOT = Path.cwd()
SEED_COMMIT = "35c8ea8565ee8528db58175cb3d16f379ea31a9b"

def git_show(path):
    return subprocess.check_output(["git","show",f"{SEED_COMMIT}:{path}"])

def restore_chunks(prefix, names):
    encoded = b"".join(git_show(f".bootstrap/{prefix}{name}").strip() for name in names)
    return lzma.decompress(base64.b64decode(encoded), format=lzma.FORMAT_XZ)

print("Restoring original bootstrap metadata from repository history")

index_seed = restore_chunks("index.html.xz.b64.", [f"{i:02d}" for i in range(21)]).decode("utf-8","ignore")
m = re.search(r'<script\s+type=["\']importmap["\'][^>]*>(.*?)</script>', index_seed, flags=re.I|re.S)
if not m:
    raise SystemExit("Original import map not found")
importmap_json = m.group(1)
print("Original import map bytes:",len(importmap_json.encode("utf-8")))

manifest_raw = restore_chunks("resources.xz.b64.", [str(i) for i in range(5)])
resources = json.loads(manifest_raw.decode("utf-8"))
print("Manifest resources:",len(resources))

path_map={}
netlify_map={}
asset_map={}
for item in resources:
    url=item.get("url") or ""
    rel=(item.get("path") or "").lstrip("/")
    if not url or not rel:
        continue
    p=urlparse(url)
    host=p.netloc.lower()
    local="/"+rel
    if host in {"www.linearity.io","linearity.io"}:
        if p.path=="/.netlify/images":
            raw=(parse_qs(p.query).get("url") or [""])[0]
            if raw:
                try:
                    u=urlparse(unquote(raw))
                    src=u.path if u.scheme else unquote(raw)
                except Exception:
                    src=unquote(raw)
                if src:
                    netlify_map[src]=local
        else:
            if p.path not in path_map or not p.query:
                path_map[p.path]=local
    elif host=="assets.linearity.io":
        asset_map[p.path]=local

path_map["/textures/LDR_RGB1_0.png"]="/textures/ldr_rgb1_0.png"
path_map["/textures/ldr_rgb1_0.png"]="/textures/ldr_rgb1_0.png"

runtime_data=json.dumps({"P":path_map,"N":netlify_map,"A":asset_map},separators=(",",":"))
site=ROOT/"__sitecloner"
site.mkdir(exist_ok=True)

# Remove old generated bootstrap files.
for p in site.glob("importmap-data-*.js"): p.unlink()
for p in site.glob("runtime-data-*.js"): p.unlink()
for p in [site/"runtime.js",site/"bootstrap.js"]:
    if p.exists(): p.unlink()

def write_encoded_parts(prefix, varname, text, chunk_chars=18000):
    parts=[]
    for i in range(0,len(text),chunk_chars):
        chunk=text[i:i+chunk_chars].encode("utf-8")
        encoded=base64.b64encode(chunk).decode("ascii")
        name=f"{prefix}-{len(parts)}.js"
        (site/name).write_text(
            f'window.{varname}=window.{varname}||[];window.{varname}.push(atob("{encoded}"));\n',
            "utf-8"
        )
        parts.append(name)
    return parts

im_parts=write_encoded_parts("importmap-data","__SC_IM",importmap_json)
rt_parts=write_encoded_parts("runtime-data","__SC_RT",runtime_data)

bootstrap = r"""(() => {
const im=(window.__SC_IM||[]).join("");
const data=JSON.parse((window.__SC_RT||[]).join(""));
const P=data.P||{}, N=data.N||{}, A=data.A||{};
const BLOCK={script:"/__sitecloner/blocked.js",style:"/__sitecloner/blocked.css",image:"/__sitecloner/pixel.svg",frame:"/__sitecloner/blank.html",media:"/__sitecloner/blank.html",data:"/__sitecloner/blocked.json"};
const SOURCE=new Set(["www.linearity.io","linearity.io"]);
const rawValue=v=>String(v&&v.url?v.url:v);
const parse=v=>{try{return new URL(rawValue(v),location.href)}catch{return null}};
function netlify(a){
  if(a.pathname!=="/.netlify/images")return null;
  try{
    const raw=a.searchParams.get("url")||"";
    const u=new URL(decodeURIComponent(raw),"https://assets.linearity.io");
    return N[u.pathname]||null;
  }catch{return null}
}
function mapResource(v){
  const a=parse(v);
  if(!a)return rawValue(v);
  if(a.protocol==="data:"||a.protocol==="blob:")return a.href;
  if(a.origin===location.origin)return a.pathname+a.search+a.hash;
  if(SOURCE.has(a.hostname)){
    const nf=netlify(a); if(nf)return nf;
    return P[a.pathname]||a.pathname;
  }
  if(a.hostname==="assets.linearity.io")return A[a.pathname]||N[a.pathname]||null;
  return null;
}
const F=window.fetch.bind(window);
window.fetch=(input,init)=>{const m=mapResource(input);if(m!==null)return F(m,init);return Promise.resolve(new Response("{}",{status:200,headers:{"content-type":"application/json"}}))};
const XO=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(method,url,...rest){const m=mapResource(url);return XO.call(this,method,m===null?BLOCK.data:m,...rest)};
for(const [Ctor,name] of [[window.Worker,"Worker"],[window.SharedWorker,"SharedWorker"]]){
  try{if(Ctor)window[name]=function(url,opts){const m=mapResource(url);return new Ctor(m===null?BLOCK.script:m,opts)}}catch{}
}
const setters=[[HTMLImageElement,"src","image"],[HTMLScriptElement,"src","script"],[HTMLLinkElement,"href","style"],[HTMLVideoElement,"src","media"],[HTMLAudioElement,"src","media"],[HTMLSourceElement,"src","media"],[HTMLIFrameElement,"src","frame"]];
for(const [Ctor,prop,kind] of setters){
  try{
    const d=Object.getOwnPropertyDescriptor(Ctor.prototype,prop);
    if(d&&d.set)Object.defineProperty(Ctor.prototype,prop,{...d,set(value){const m=mapResource(value);return d.set.call(this,m===null?BLOCK[kind]:m)}})
  }catch{}
}
const SA=Element.prototype.setAttribute;
Element.prototype.setAttribute=function(name,value){
  const n=String(name).toLowerCase();
  if(n==="src"||n==="data"||(n==="href"&&!(this instanceof HTMLAnchorElement))){
    const m=mapResource(value);
    if(m!==null)value=m;
    else if(this instanceof HTMLScriptElement)value=BLOCK.script;
    else if(this instanceof HTMLLinkElement)value=BLOCK.style;
    else if(this instanceof HTMLImageElement)value=BLOCK.image;
    else if(this instanceof HTMLIFrameElement)value=BLOCK.frame;
    else value=BLOCK.data;
  }
  return SA.call(this,name,value)
};
window.__SITECLONER_LOCAL__={pathMap:P,netlifyMap:N,assetMap:A};
const mapScript=document.createElement("script");
mapScript.type="importmap";
mapScript.textContent=im;
document.currentScript.before(mapScript);
})();"""
(site/"bootstrap.js").write_text(bootstrap,"utf-8")
(site/"blocked.js").write_text("/* intentionally local-blocked external script */\n","utf-8")
(site/"blocked.css").write_text("/* intentionally local-blocked external stylesheet */\n","utf-8")
(site/"blocked.json").write_text("{}\n","utf-8")
(site/"blank.html").write_text("<!doctype html><meta charset=utf-8>\n","utf-8")
(site/"pixel.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>\n',"utf-8")

idx=ROOT/"index.html"
html=idx.read_text("utf-8","ignore")

# Remove any previous direct import-map/runtime/bootstrap tags.
html=re.sub(r'<script\s+type=["\']importmap["\'][^>]*>.*?</script>','',html,flags=re.I|re.S)
html=re.sub(r'<script[^>]+src=["\']/__sitecloner/(?:runtime|bootstrap)\.js["\'][^>]*>\s*</script>','',html,flags=re.I|re.S)
html=re.sub(r'<script[^>]+src=["\']/__sitecloner/(?:importmap-data|runtime-data)-\d+\.js["\'][^>]*>\s*</script>','',html,flags=re.I|re.S)

# Install local bootstrap at the very beginning of head, before modulepreloads/module execution.
tags=[]
for name in im_parts:
    tags.append(f'<script src="/__sitecloner/{name}"></script>')
for name in rt_parts:
    tags.append(f'<script src="/__sitecloner/{name}"></script>')
tags.append('<script src="/__sitecloner/bootstrap.js"></script>')
inject="".join(tags)
if "<head>" not in html:
    raise SystemExit("head tag missing")
html=html.replace("<head>","<head>"+inject,1)
idx.write_text(html,"utf-8")

# Remove CSP from Vercel config. Local runtime handles resource confinement.
vp=ROOT/"vercel.json"
cfg={}
if vp.exists():
    try: cfg=json.loads(vp.read_text("utf-8"))
    except Exception: cfg={}
headers=[]
for rule in cfg.get("headers",[]):
    kept=[h for h in rule.get("headers",[]) if h.get("key","").lower()!="content-security-policy"]
    if kept:
        rule["headers"]=kept
        headers.append(rule)
cfg["cleanUrls"]=False
cfg["headers"]=headers or [{"source":"/(.*)","headers":[{"key":"X-Content-Type-Options","value":"nosniff"},{"key":"Referrer-Policy","value":"no-referrer"}]}]
vp.write_text(json.dumps(cfg,indent=2)+"\n","utf-8")

# Static validation.
check=idx.read_text("utf-8","ignore")
if "/__sitecloner/bootstrap.js" not in check:
    raise SystemExit("bootstrap missing")
if re.search(r'<script\s+type=["\']importmap["\']',check,re.I):
    raise SystemExit("raw import map unexpectedly remains")
if not re.search(r'/_nuxt/entry\.[^"\']+\.js',check):
    raise SystemExit("Nuxt entry missing")

refs=set()
for mm in re.finditer(r'(?:src|href)=["\'](/[^"\']+)["\']',check,re.I):
    ref=mm.group(1).split("#",1)[0].split("?",1)[0]
    if ref=="/" or ref.startswith("//"):continue
    if any(ref.lower().endswith(ext) for ext in (".js",".css",".png",".jpg",".jpeg",".webp",".svg",".woff",".woff2",".ico",".json",".webmanifest")):
        refs.add(ref)
missing=[r for r in sorted(refs) if not (ROOT/r.lstrip("/")).exists()]
if missing:
    print("Missing homepage refs",missing[:50])
    raise SystemExit("local homepage refs missing")

print("REPAIRED_INDEX_BYTES",idx.stat().st_size)
print("IMPORTMAP_PARTS",len(im_parts),"RUNTIME_PARTS",len(rt_parts))
print("BOOTSTRAP_BYTES",(site/"bootstrap.js").stat().st_size)
print("LOCAL_REFS",len(refs))
print("PATH_MAP",len(path_map),"NETLIFY_MAP",len(netlify_map),"ASSET_MAP",len(asset_map))
