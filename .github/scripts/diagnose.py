import asyncio, json
from playwright.async_api import async_playwright

LOCAL="http://127.0.0.1:8123"

async def main():
    ext=[]; failed=[]; page_errors=[]; console=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--enable-webgl","--ignore-gpu-blocklist","--use-gl=swiftshader"])
        page=await browser.new_page(viewport={"width":1440,"height":1000})
        page.on("request",lambda r: ext.append({"url":r.url,"type":r.resource_type}) if r.url.startswith("http") and not r.url.startswith(LOCAL) else None)
        page.on("requestfailed",lambda r: failed.append({"url":r.url,"type":r.resource_type,"failure":r.failure}))
        page.on("pageerror",lambda e: page_errors.append(str(e)))
        page.on("console",lambda m: console.append({"type":m.type,"text":m.text}) if m.type in ("error","warning") else None)
        resp=await page.goto(LOCAL+"/",wait_until="domcontentloaded",timeout=90000)
        await page.wait_for_timeout(2500)
        a1=await page.evaluate("""() => document.getAnimations().map((a,i)=>({i,t:Number(a.currentTime||0)}))""")
        await page.wait_for_timeout(900)
        a2=await page.evaluate("""() => document.getAnimations().map((a,i)=>({i,t:Number(a.currentTime||0)}))""")
        advancing=sum(1 for x in a1 for y in a2 if x["i"]==y["i"] and y["t"]>x["t"]+20)
        height=await page.evaluate("document.documentElement.scrollHeight")
        for y in range(0,min(height,18000),650):
            await page.evaluate("(y)=>window.scrollTo(0,y)",y)
            await page.wait_for_timeout(90)
        await page.wait_for_timeout(1200)
        metrics=await page.evaluate("""() => ({
          title:document.title,
          canvas:document.querySelectorAll('canvas').length,
          anims:document.getAnimations().length,
          height:document.documentElement.scrollHeight,
          nuxt:!!document.querySelector('#__nuxt'),
          localRuntime:!!window.__SITECLONER_LOCAL__,
          text:(document.body.innerText||'').slice(0,140)
        })""")
        print(json.dumps({
          "status":resp.status if resp else None,
          "metrics":metrics,
          "advancing":advancing,
          "external_count":len(ext),
          "external":ext[:120],
          "failed":failed[:60],
          "page_errors":page_errors,
          "console":console[:80]
        },indent=2))
        await browser.close()
    if page_errors:
        raise SystemExit("page errors")
    if not metrics["nuxt"] or not metrics["localRuntime"]:
        raise SystemExit("bootstrap missing")
    if metrics["anims"]<5 or advancing<3:
        raise SystemExit("animations not active")

asyncio.run(main())
