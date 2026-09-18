import asyncio, json, sys
from playwright.async_api import async_playwright

LOCAL_PREFIX="http://127.0.0.1:8123"
async def main():
    console_errors=[]
    page_errors=[]
    failed=[]
    external=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={"width":1440,"height":1000})
        await page.add_init_script("""
          window.__RAF_COUNT__=0;
          const __nativeRAF=window.requestAnimationFrame.bind(window);
          window.requestAnimationFrame=(cb)=>__nativeRAF((t)=>{window.__RAF_COUNT__++; return cb(t)});
        """)
        page.on("console",lambda m: console_errors.append(m.text) if m.type=="error" else None)
        page.on("pageerror",lambda e: page_errors.append(str(e)))
        page.on("requestfailed",lambda r: failed.append({"url":r.url,"failure":r.failure,"type":r.resource_type}))
        def req(r):
            if r.url.startswith("http") and not r.url.startswith(LOCAL_PREFIX):
                if r.resource_type in {"script","stylesheet","image","font","media","xhr","fetch","worker"}:
                    external.append({"url":r.url,"type":r.resource_type})
        page.on("request",req)

        response=await page.goto(LOCAL_PREFIX+"/",wait_until="domcontentloaded",timeout=90000)
        if not response or response.status>=400:
            raise RuntimeError(f"homepage status {response.status if response else 'none'}")
        await page.wait_for_timeout(4500)
        height=await page.evaluate("document.documentElement.scrollHeight")
        limit=min(height,18000)
        for y in range(0,limit,650):
            await page.evaluate("(y)=>window.scrollTo(0,y)",y)
            await page.wait_for_timeout(90)
        await page.wait_for_timeout(1800)
        metrics=await page.evaluate("""() => ({
          title:document.title,
          height:document.documentElement.scrollHeight,
          nuxt:!!document.querySelector('#__nuxt'),
          canvas:document.querySelectorAll('canvas').length,
          video:document.querySelectorAll('video').length,
          webAnimations:document.getAnimations().length,
          raf:window.__RAF_COUNT__||0,
          localRuntime:!!window.__SITECLONER_LOCAL__,
          scripts:[...document.scripts].map(s=>s.src).filter(Boolean),
          text:(document.body.innerText||'').slice(0,180)
        })""")
        perf=await page.evaluate("""() => performance.getEntriesByType('resource').map(x=>x.name).filter(x=>x.includes('/_nuxt/'))""")
        await browser.close()

    fatal_console=[x for x in console_errors if any(k in x.lower() for k in [
        "failed to resolve module specifier","import map","uncaught syntaxerror","uncaught referenceerror","uncaught typeerror"
    ])]
    local_failed=[x for x in failed if x["url"].startswith(LOCAL_PREFIX)]
    result={
        "metrics":metrics,
        "nuxtResources":len(perf),
        "pageErrors":page_errors,
        "fatalConsole":fatal_console,
        "localFailed":local_failed[:30],
        "externalLoadBearing":external[:30]
    }
    print(json.dumps(result,indent=2))
    if not metrics["nuxt"] or not metrics["localRuntime"]:
        raise SystemExit("Nuxt/runtime bootstrap did not initialize")
    if metrics["canvas"] < 1:
        raise SystemExit("WebGL/animation canvas did not initialize")
    if metrics["raf"] < 20:
        raise SystemExit(f"Animation frame activity too low: {metrics['raf']}")
    if len(perf) < 20:
        raise SystemExit(f"Too few Nuxt modules loaded: {len(perf)}")
    if page_errors:
        raise SystemExit("Browser page errors detected")
    if fatal_console:
        raise SystemExit("Fatal module/runtime console errors detected")
    if local_failed:
        raise SystemExit("Local resource requests failed")
    if external:
        raise SystemExit("Outbound load-bearing requests detected")

asyncio.run(main())
