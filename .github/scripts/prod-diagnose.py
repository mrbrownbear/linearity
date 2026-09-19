import asyncio, json
from playwright.async_api import async_playwright
URL="https://linearity-three.vercel.app/"
async def main():
    failed=[]; errors=[]; console=[]; responses=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--enable-webgl","--ignore-gpu-blocklist","--use-gl=swiftshader"])
        page=await browser.new_page(viewport={"width":1440,"height":1000})
        page.on("requestfailed",lambda r: failed.append({"url":r.url,"type":r.resource_type,"failure":r.failure}))
        page.on("pageerror",lambda e: errors.append(str(e)))
        page.on("console",lambda m: console.append({"type":m.type,"text":m.text}) if m.type in ("error","warning") else None)
        page.on("response",lambda r: responses.append({"url":r.url,"status":r.status}) if "linearity-three.vercel.app" in r.url else None)
        resp=await page.goto(URL,wait_until="domcontentloaded",timeout=90000)
        await page.wait_for_timeout(3000)
        a1=await page.evaluate("""() => document.getAnimations().map((a,i)=>({i,t:Number(a.currentTime||0)}))""")
        style1=await page.evaluate("""() => [...document.querySelectorAll('body *')].slice(0,1200).map((e,i)=>{const s=getComputedStyle(e);return [i,s.transform,s.opacity]})""")
        await page.wait_for_timeout(900)
        a2=await page.evaluate("""() => document.getAnimations().map((a,i)=>({i,t:Number(a.currentTime||0)}))""")
        advancing=sum(1 for x in a1 for y in a2 if x["i"]==y["i"] and y["t"]>x["t"]+20)
        height=await page.evaluate("document.documentElement.scrollHeight")
        target=min(max(1400,height//5),5000)
        await page.evaluate("(y)=>window.scrollTo(0,y)",target)
        await page.wait_for_timeout(1000)
        style2=await page.evaluate("""() => [...document.querySelectorAll('body *')].slice(0,1200).map((e,i)=>{const s=getComputedStyle(e);return [i,s.transform,s.opacity]})""")
        b={x[0]:(x[1],x[2]) for x in style1}
        changes=sum(1 for x in style2 if x[0] in b and b[x[0]]!=(x[1],x[2]))
        metrics=await page.evaluate("""() => ({
          title:document.title,
          height:document.documentElement.scrollHeight,
          canvas:document.querySelectorAll('canvas').length,
          anims:document.getAnimations().length,
          nuxt:!!document.querySelector('#__nuxt'),
          localRuntime:!!window.__SITECLONER_LOCAL__,
          bootstrap:[...document.scripts].map(s=>s.src).filter(x=>x.includes('__sitecloner')),
          entry:[...document.scripts].map(s=>s.src).find(x=>x.includes('/_nuxt/entry.'))||null,
          text:(document.body.innerText||'').slice(0,140)
        })""")
        print(json.dumps({
          "status":resp.status if resp else None,
          "metrics":metrics,
          "advancing":advancing,
          "scrollStyleChanges":changes,
          "failed":failed[:80],
          "page_errors":errors,
          "console":console[:100],
          "responses":responses[:60]
        },indent=2))
        await browser.close()
asyncio.run(main())
