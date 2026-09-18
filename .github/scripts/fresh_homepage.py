import asyncio, hashlib, json, os, re, shutil, subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from playwright.async_api import async_playwright

ROOT = Path.cwd()
OUT = ROOT / ".fresh_capture"
SOURCE_HOSTS = {"www.linearity.io", "linearity.io", "assets.linearity.io"}
BLOCK_HOST_BITS = (
    "googletagmanager", "google-analytics", "analytics.google", "doubleclick",
    "facebook.net", "hotjar", "clarity.ms", "hubspot", "segment", "sentry",
    "intercom", "cookiebot", "lemlist"
)
CAPTURE_TYPES = {"document","stylesheet","script","image","font","media","xhr","fetch"}
url_to_local = {}
local_to_url = {}
saved = set()
root_document = None

def blocked_host(host):
    h=(host or "").lower()
    return any(x in h for x in BLOCK_HOST_BITS)

def local_path_for(url):
    u=urlparse(url)
    host=u.netloc.lower()
    path=u.path or "/"
    if path.endswith("/"):
        path += "index.html"
    name=Path(path).name or "asset"
    parent=Path(path.lstrip("/")).parent
    if u.query:
        p=Path(name)
        q=hashlib.sha1(u.query.encode()).hexdigest()[:10]
        name=f"{p.stem}__q_{q}{p.suffix}"
    if host in {"www.linearity.io","linearity.io"}:
        rel=parent/name
    elif host=="assets.linearity.io":
        rel=Path("__assets_linearity")/parent/name
    else:
        rel=Path("__external__")/host/parent/name
    return rel.as_posix()

async def main():
    global root_document
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    tasks=set()
    sem=asyncio.Semaphore(16)

    async def save_response(resp):
        nonlocal tasks
        try:
            req=resp.request
            url=resp.url
            u=urlparse(url)
            if u.scheme not in {"http","https"} or blocked_host(u.netloc):
                return
            if req.resource_type not in CAPTURE_TYPES:
                return
            if resp.status < 200 or resp.status >= 400:
                return
            # Keep homepage assets and any asset response the homepage actually requested.
            if req.resource_type=="document" and u.netloc not in {"www.linearity.io","linearity.io"}:
                return
            async with sem:
                body=await resp.body()
                if not body:
                    return
                rel=local_path_for(url)
                dest=OUT/rel
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(body)
                url_to_local[url]="/"+rel
                local_to_url[rel]=url
                saved.add(rel)
        except Exception as e:
            print("SAVE_WARN", getattr(resp,"url",""), type(e).__name__)

    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        context=await browser.new_context(
            viewport={"width":1440,"height":1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36"
        )
        page=await context.new_page()

        def on_response(resp):
            t=asyncio.create_task(save_response(resp))
            tasks.add(t)
            t.add_done_callback(tasks.discard)
        page.on("response", on_response)

        print("NAVIGATE")
        resp=await page.goto("https://www.linearity.io/", wait_until="domcontentloaded", timeout=120000)
        if not resp or resp.status >= 400:
            raise RuntimeError(f"homepage failed: {resp.status if resp else 'no response'}")

        await page.wait_for_timeout(2500)
        height=await page.evaluate("document.documentElement.scrollHeight")
        y=0
        while y < height:
            await page.evaluate("(y)=>window.scrollTo(0,y)", y)
            await page.wait_for_timeout(250)
            y += 850
            height=max(height, await page.evaluate("document.documentElement.scrollHeight"))
        await page.evaluate("window.scrollTo(0,0)")
        await page.wait_for_timeout(2500)

        # Capture the browser's final HTML as a fallback, but prefer the original document response below.
        rendered=await page.content()
        (OUT/"rendered.html").write_text(rendered,"utf-8")
        await browser.close()

    if tasks:
        await asyncio.gather(*list(tasks), return_exceptions=True)

    # Locate captured root document and normalize it to index.html.
    candidates=[OUT/"index.html", OUT/"index__q_"+""]
    index=OUT/"index.html"
    if not index.exists():
        docs=[p for p in OUT.rglob("index.html") if "__external__" not in p.parts]
        if docs:
            shutil.copyfile(docs[0], index)
    if not index.exists():
        shutil.copyfile(OUT/"rendered.html", index)

    html=index.read_text("utf-8",errors="ignore")

    # Remove trackers and any scripts whose only purpose is analytics.
    html=re.sub(r'<(?:script|iframe|img)[^>]+(?:googletagmanager|google-analytics|hotjar|hubspot|cookiebot|lemlist|clarity)[^>]*>(?:.*?</script>)?','',html,flags=re.I|re.S)

    # Rewrite exact captured URLs first.
    for url,local in sorted(url_to_local.items(), key=lambda kv: len(kv[0]), reverse=True):
        html=html.replace(url,local)
        html=html.replace(url.replace("&","&amp;"),local)

    # Rewrite protocol-relative source asset URLs.
    html=html.replace("//www.linearity.io/_nuxt/","/_nuxt/")
    html=html.replace("//linearity.io/_nuxt/","/_nuxt/")
    html=html.replace("https://www.linearity.io/_nuxt/","/_nuxt/")
    html=html.replace("https://linearity.io/_nuxt/","/_nuxt/")

    # Strong local-only policy for runtime resources. External navigation links remain clickable.
    csp="default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline' data:; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' data: blob:; connect-src 'self' data: blob:; frame-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'self';"
    html=re.sub(r'<meta[^>]+http-equiv=["\']Content-Security-Policy["\'][^>]*>','',html,flags=re.I)
    if "<head>" in html:
        html=html.replace("<head>",'<head><meta http-equiv="Content-Security-Policy" content="'+csp+'">',1)

    index.write_text(html,"utf-8")
    try:
        (OUT/"rendered.html").unlink()
    except FileNotFoundError:
        pass

    # Rewrite text assets using the same captured URL map.
    text_ext={".html",".css",".js",".mjs",".json",".svg",".xml",".txt",".webmanifest",".map"}
    for pth in list(OUT.rglob("*")):
        if not pth.is_file() or pth.suffix.lower() not in text_ext:
            continue
        try:
            s=pth.read_text("utf-8")
        except Exception:
            continue
        orig=s
        for url,local in sorted(url_to_local.items(), key=lambda kv: len(kv[0]), reverse=True):
            s=s.replace(url,local)
            s=s.replace(url.replace("&","&amp;"),local)
        s=s.replace("https://www.linearity.io/_nuxt/","/_nuxt/")
        s=s.replace("https://linearity.io/_nuxt/","/_nuxt/")
        # Remove obvious credential-shaped strings if any third-party code happens to contain them.
        s=re.sub(r'ghs_[A-Za-z0-9._-]{20,}','credential_removed',s,flags=re.I)
        s=re.sub(r'github_pat_[A-Za-z0-9_-]{20,}','credential_removed',s,flags=re.I)
        if s!=orig:
            pth.write_text(s,"utf-8")

    # Create deployment config.
    (OUT/"vercel.json").write_text(json.dumps({
        "cleanUrls": False,
        "headers": [{"source":"/(.*)","headers":[
            {"key":"X-Content-Type-Options","value":"nosniff"},
            {"key":"Referrer-Policy","value":"no-referrer"},
            {"key":"Permissions-Policy","value":"camera=(), microphone=(), geolocation=()"}
        ]}]
    },indent=2)+"\n","utf-8")
    (OUT/"README.md").write_text("# Linearity homepage snapshot\n\nFresh homepage-only capture with runtime assets stored locally in this repository.\n","utf-8")

    # Static reference validation for root HTML.
    check=index.read_text("utf-8",errors="ignore")
    if len(check)<50000:
        raise RuntimeError("captured homepage is unexpectedly small")
    if "One prompt" not in check and "linearity" not in check.lower():
        raise RuntimeError("captured homepage content validation failed")

    refs=set()
    for m in re.finditer(r'(?:src|href)=["\'](/[^"\']+)["\']',check,re.I):
        ref=m.group(1).split("#",1)[0].split("?",1)[0]
        if ref.startswith("//") or ref=="/":
            continue
        refs.add(ref)
    missing=[]
    for ref in refs:
        rp=OUT/ref.lstrip("/")
        if not rp.exists() and any(ref.lower().endswith(x) for x in (".js",".css",".png",".jpg",".jpeg",".webp",".svg",".woff",".woff2",".ico",".json",".webmanifest")):
            missing.append(ref)
    print("CAPTURED_FILES",sum(1 for p in OUT.rglob("*") if p.is_file()))
    print("HTML_BYTES",index.stat().st_size)
    print("MISSING_STATIC_REFS",len(missing))
    if missing[:30]:
        print("MISSING_SAMPLE",missing[:30])

    # Replace repository with the fresh capture, preserving .git only.
    for child in ROOT.iterdir():
        if child.name in {".git",".fresh_capture"}:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for child in OUT.iterdir():
        target=ROOT/child.name
        shutil.move(str(child),str(target))
    shutil.rmtree(OUT,ignore_errors=True)

    subprocess.run(["git","config","user.name","github-actions[bot]"],check=True)
    subprocess.run(["git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com"],check=True)
    subprocess.run(["git","add","-A"],check=True)
    subprocess.run(["git","commit","-m","Fresh homepage-only Linearity capture"],check=True)
    subprocess.run(["git","push","origin","HEAD:main"],check=True)

asyncio.run(main())
