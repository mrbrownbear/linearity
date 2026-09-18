import asyncio, json, sys
from playwright.async_api import async_playwright

LOCAL_PREFIX="http://127.0.0.1:8123"
async def main():
    console_errors=[]
    page_errors=[]
    failed=[]
    external=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--enable-webgl","--ignore-gpu-blocklist","--use-gl=swiftshader"])
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
        await page.wait_for_timeout(1200)
        anim_before=await page.evaluate("""() => document.getAnimations().map((a,i)=>({i,t:Number(a.currentTime||0),state:a.playState}))""")
        style_before=await page.evaluate("""() => [...document.querySelectorAll('body *')].slice(0,1200).map((el,i)=>{const s=getComputedStyle(el);return [i,s.transform,s.opacity]})""")
        await page.wait_for_timeout(700)
        anim_after=await page.evaluate("""() => document.getAnimations().map((a,i)=>({i,t:Number(a.currentTime||0),state:a.playState}))""")
        advancing=sum(1 for a in anim_before for b in anim_after if a["i"]==b["i"] and b["t"]>a["t"]+20)

        height=await page.evaluate("document.documentElement.scrollHeight")
        target=min(max(1400,height//5),5000)
        await page.evaluate("(y)=>window.scrollTo(0,y)",target)
        await page.wait_for_timeout(900)
        style_after=await page.evaluate("""() => [...document.querySelectorAll('body *')].slice(0,1200).map((el,i)=>{const s=getComputedStyle(el);return [i,s.transform,s.opacity]})""")
        before_map={x[0]:(x[1],x[2]) for x in style_before}
        style_changes=sum(1 for x in style_after if x[0] in before_map and before_map[x[0]]!=(x[1],x[2]))

        limit=min(height,18000)
        for y in range(target,limit,650):
            await page.evaluate("(y)=>window.scrollTo(0,y)",y)
            await page.wait_for_timeout(80)
        await page.wait_for_timeout(900)
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
        "advancingAnimations":advancing,
        "scrollStyleChanges":style_changes,
        "nuxtResources":len(perf),
        "pageErrors":page_errors,
        "fatalConsole":fatal_console,
        "localFailed":local_failed[:30],
        "externalLoadBearing":external[:30]
    }
    print(json.dumps(result,indent=2))
    if not metrics["nuxt"] or not metrics["localRuntime"]:
        raise SystemExit("Nuxt/runtime bootstrap did not initialize")
    if metrics["webAnimations"] < 5:
        raise SystemExit(f"Too few browser animations initialized: {metrics['webAnimations']}")
    if advancing < 3:
        raise SystemExit(f"Animations are not advancing: {advancing}")
    if style_changes < 3:
        raise SystemExit(f"Scroll did not trigger visible style changes: {style_changes}")
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
