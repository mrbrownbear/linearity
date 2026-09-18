from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import base64, json, lzma, re, shutil, subprocess, sys

ROOT = Path.cwd()
SEED_COMMIT = "35c8ea8565ee8528db58175cb3d16f379ea31a9b"

def git_show(path):
    return subprocess.check_output(["git","show",f"{SEED_COMMIT}:{path}"])

def restore_chunks(prefix, names):
    encoded = b"".join(git_show(f".bootstrap/{prefix}{name}").strip() for name in names)
    return lzma.decompress(base64.b64decode(encoded), format=lzma.FORMAT_XZ)

print("Restoring original bootstrap metadata from repository history")

# Exact original homepage seed, used only to recover the import map.
index_seed = restore_chunks("index.html.xz.b64.", [f"{i:02d}" for i in range(21)]).decode("utf-8", "ignore")
m = re.search(r'<script\s+type=["\']importmap["\'][^>]*>.*?</script>', index_seed, flags=re.I|re.S)
if not m:
    raise SystemExit("Original import map not found in seed")
importmap_tag = m.group(0)
print("Original import map bytes:", len(importmap_tag.encode("utf-8")))

# Exact captured resource manifest, used to create a safe path-only local mapper.
manifest_raw = restore_chunks("resources.xz.b64.", [str(i) for i in range(5)])
resources = json.loads(manifest_raw.decode("utf-8"))
print("Manifest resources:", len(resources))

# Build path mappings without embedding tracking/token query strings.
path_map = {}
netlify_map = {}
asset_map = {}
for item in resources:
    url = item.get("url") or ""
    rel = (item.get("path") or "").lstrip("/")
    if not url or not rel:
        continue
    p = urlparse(url)
    host = p.netloc.lower()
    local = "/" + rel
    if host in {"www.linearity.io", "linearity.io"}:
        if p.path == "/.netlify/images":
            qs = parse_qs(p.query)
            src = (qs.get("url") or [""])[0]
            if src:
                try:
                    su = urlparse(unquote(src))
                    source_path = su.path if su.scheme else unquote(src)
                except Exception:
                    source_path = unquote(src)
                if source_path:
                    netlify_map[source_path] = local
        else:
            # Only path-based mappings. If a path occurs with multiple query variants,
            # prefer the query-free capture where available.
            if p.path not in path_map or not p.query:
                path_map[p.path] = local
    elif host == "assets.linearity.io":
        asset_map[p.path] = local

# Explicit case-sensitive texture aliases used by WebGL.
path_map["/textures/LDR_RGB1_0.png"] = "/textures/ldr_rgb1_0.png"
path_map["/textures/ldr_rgb1_0.png"] = "/textures/ldr_rgb1_0.png"

runtime = """(() => {
const P=__PATH_MAP__;
const N=__NETLIFY_MAP__;
const A=__ASSET_MAP__;
const BLOCK={
  script:"/__sitecloner/blocked.js",
  style:"/__sitecloner/blocked.css",
  image:"/__sitecloner/pixel.svg",
  frame:"/__sitecloner/blank.html",
  media:"/__sitecloner/blank.html",
  data:"/__sitecloner/blocked.json"
};
const SOURCE=new Set(["www.linearity.io","linearity.io"]);
const rawValue=v=>String(v&&v.url?v.url:v);
const parse=v=>{try{return new URL(rawValue(v),location.href)}catch{return null}};
function netlify(a){
  if(a.pathname!=="/.netlify/images") return null;
  try{
    const raw=a.searchParams.get("url")||"";
    const decoded=decodeURIComponent(raw);
    const u=new URL(decoded,"https://assets.linearity.io");
    return N[u.pathname]||null;
  }catch{return null}
}
function mapResource(v){
  const a=parse(v);
  if(!a) return rawValue(v);
  if(a.protocol==="data:"||a.protocol==="blob:") return a.href;
  if(a.origin===location.origin) return a.pathname+a.search+a.hash;
  if(SOURCE.has(a.hostname)){
    const nf=netlify(a); if(nf) return nf;
    return P[a.pathname] || a.pathname;
  }
  if(a.hostname==="assets.linearity.io"){
    return A[a.pathname] || N[a.pathname] || null;
  }
  return null;
}
const nativeFetch=window.fetch.bind(window);
window.fetch=(input,init)=>{
  const mapped=mapResource(input);
  if(mapped!==null) return nativeFetch(mapped,init);
  return Promise.resolve(new Response("{}",{status:200,headers:{"content-type":"application/json"}}));
};
const xo=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(method,url,...rest){
  const mapped=mapResource(url);
  return xo.call(this,method,mapped===null?BLOCK.data:mapped,...rest);
};
for(const [Ctor,name] of [[window.Worker,"Worker"],[window.SharedWorker,"SharedWorker"]]){
  try{
    if(Ctor) window[name]=function(url,opts){
      const mapped=mapResource(url);
      return new Ctor(mapped===null?BLOCK.script:mapped,opts);
    };
  }catch{}
}
const setters=[
  [HTMLImageElement,"src","image"],
  [HTMLScriptElement,"src","script"],
  [HTMLLinkElement,"href","style"],
  [HTMLVideoElement,"src","media"],
  [HTMLAudioElement,"src","media"],
  [HTMLSourceElement,"src","media"],
  [HTMLIFrameElement,"src","frame"]
];
for(const [Ctor,prop,kind] of setters){
  try{
    const d=Object.getOwnPropertyDescriptor(Ctor.prototype,prop);
    if(d&&d.set) Object.defineProperty(Ctor.prototype,prop,{...d,set(value){
      const mapped=mapResource(value);
      return d.set.call(this,mapped===null?BLOCK[kind]:mapped);
    }});
  }catch{}
}
const nativeSetAttribute=Element.prototype.setAttribute;
Element.prototype.setAttribute=function(name,value){
  const n=String(name).toLowerCase();
  if(n==="src"||n==="data"||(n==="href" && !(this instanceof HTMLAnchorElement))){
    const mapped=mapResource(value);
    if(mapped!==null) value=mapped;
    else if(this instanceof HTMLScriptElement) value=BLOCK.script;
    else if(this instanceof HTMLLinkElement) value=BLOCK.style;
    else if(this instanceof HTMLImageElement) value=BLOCK.image;
    else if(this instanceof HTMLIFrameElement) value=BLOCK.frame;
    else value=BLOCK.data;
  }
  return nativeSetAttribute.call(this,name,value);
};
window.__SITECLONER_LOCAL__={pathMap:P,netlifyMap:N,assetMap:A};
})();"""
runtime = runtime.replace("__PATH_MAP__", json.dumps(path_map,separators=(",",":")))
runtime = runtime.replace("__NETLIFY_MAP__", json.dumps(netlify_map,separators=(",",":")))
runtime = runtime.replace("__ASSET_MAP__", json.dumps(asset_map,separators=(",",":")))

sitecloner = ROOT / "__sitecloner"
sitecloner.mkdir(exist_ok=True)
(sitecloner/"runtime.js").write_text(runtime,"utf-8")
(sitecloner/"blocked.js").write_text("/* intentionally local-blocked external script */\n","utf-8")
(sitecloner/"blocked.css").write_text("/* intentionally local-blocked external stylesheet */\n","utf-8")
(sitecloner/"blocked.json").write_text("{}\n","utf-8")
(sitecloner/"blank.html").write_text("<!doctype html><meta charset=utf-8>\n","utf-8")
(sitecloner/"pixel.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>\n',"utf-8")

idx = ROOT / "index.html"
html = idx.read_text("utf-8","ignore")

# Restore the original import map before the Nuxt module entry.
if not re.search(r'<script\s+type=["\']importmap["\']', html, flags=re.I):
    entry = re.search(r'<script[^>]+src=["\']/_nuxt/entry\.[^"\']+["\'][^>]*>\s*</script>', html, flags=re.I)
    if not entry:
        raise SystemExit("Nuxt entry script not found")
    html = html[:entry.start()] + importmap_tag + '<script src="/__sitecloner/runtime.js"></script>' + html[entry.start():]
else:
    if "/__sitecloner/runtime.js" not in html:
        im = re.search(r'<script\s+type=["\']importmap["\'][^>]*>.*?</script>', html, flags=re.I|re.S)
        html = html[:im.end()] + '<script src="/__sitecloner/runtime.js"></script>' + html[im.end():]

# Ensure runtime loads before Nuxt entry even if another old runtime tag exists elsewhere.
html = re.sub(r'<script[^>]+src=["\']/__sitecloner/runtime\.js["\'][^>]*></script>', '', html, flags=re.I)
entry = re.search(r'<script[^>]+src=["\']/_nuxt/entry\.[^"\']+["\'][^>]*></script>', html, flags=re.I)
if not entry:
    raise SystemExit("Nuxt entry script disappeared")
html = html[:entry.start()] + '<script src="/__sitecloner/runtime.js"></script>' + html[entry.start():]

idx.write_text(html,"utf-8")

# Remove CSP from Vercel config. The working clone has no CSP and the runtime performs
# local resource mapping/blocking without restricting WebGL/worker/browser APIs.
vp = ROOT/"vercel.json"
cfg = {}
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
cfg["headers"]=headers or [{
    "source":"/(.*)",
    "headers":[
        {"key":"X-Content-Type-Options","value":"nosniff"},
        {"key":"Referrer-Policy","value":"no-referrer"}
    ]
}]
vp.write_text(json.dumps(cfg,indent=2)+"\n","utf-8")

# Static validation of the exact bootstrap chain.
check=idx.read_text("utf-8","ignore")
if not re.search(r'<script\s+type=["\']importmap["\']',check,re.I):
    raise SystemExit("import map missing after repair")
if "/__sitecloner/runtime.js" not in check:
    raise SystemExit("runtime missing after repair")
if not re.search(r'/_nuxt/entry\.[^"\']+\.js',check):
    raise SystemExit("Nuxt entry missing after repair")

# Validate load-bearing local refs in the homepage.
refs=set()
for m in re.finditer(r'(?:src|href)=["\'](/[^"\']+)["\']',check,re.I):
    ref=m.group(1).split("#",1)[0].split("?",1)[0]
    if ref=="/" or ref.startswith("//"): continue
    if any(ref.lower().endswith(ext) for ext in (".js",".css",".png",".jpg",".jpeg",".webp",".svg",".woff",".woff2",".ico",".json",".webmanifest")):
        refs.add(ref)
missing=[r for r in sorted(refs) if not (ROOT/r.lstrip("/")).exists()]
if missing:
    print("Missing homepage refs:",missing[:50])
    raise SystemExit("local homepage refs missing")

# All modulepreloads must exist.
preloads=re.findall(r'<link[^>]+rel=["\'][^"\']*modulepreload[^"\']*["\'][^>]+href=["\'](/[^"\']+)["\']',check,re.I)
missing_pre=[r for r in preloads if not (ROOT/r.split("?",1)[0].lstrip("/")).exists()]
if missing_pre:
    print("Missing modulepreloads:",missing_pre[:50])
    raise SystemExit("module preload files missing")

print("REPAIRED_INDEX_BYTES",idx.stat().st_size)
print("RUNTIME_BYTES",(sitecloner/"runtime.js").stat().st_size)
print("MODULE_PRELOADS",len(preloads))
print("LOCAL_REFS",len(refs))
print("PATH_MAP",len(path_map),"NETLIFY_MAP",len(netlify_map),"ASSET_MAP",len(asset_map))
