import asyncio, json
from playwright.async_api import async_playwright

URLS=[("prod","https://linearity-two.vercel.app/"),("local","http://127.0.0.1:8123/")]

async def test(label,url):
    reqs=[]; responses=[]; failed=[]; errors=[]; console=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--enable-webgl","--ignore-gpu-blocklist","--use-gl=swiftshader"])
        page=await browser.new_page(viewport={"width":1760,"height":950})
        page.on("request",lambda r:reqs.append({"url":r.url,"type":r.resource_type}) if ("how_it_works" in r.url or "lottie" in r.url.lower()) else None)
        page.on("response",lambda r:responses.append({"url":r.url,"status":r.status,"ct":r.headers.get("content-type","")}) if ("how_it_works" in r.url or "lottie" in r.url.lower()) else None)
        page.on("requestfailed",lambda r:failed.append({"url":r.url,"failure":r.failure,"type":r.resource_type}))
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.on("console",lambda m:console.append({"type":m.type,"text":m.text}) if m.type in ("error","warning") else None)
        resp=await page.goto(url,wait_until="domcontentloaded",timeout=90000)
        await page.wait_for_timeout(2500)
        found=await page.locator(".home-how-it-works-kp").count()
        if found:
            await page.locator(".home-how-it-works-kp").scroll_into_view_if_needed()
            await page.wait_for_timeout(4500)
        info=await page.evaluate("""() => {
          const sec=document.querySelector('.home-how-it-works-kp');
          const box=document.querySelector('.home-hiw-img-box');
          return {
            title:document.title,
            statusText:(document.body.innerText||'').slice(0,100),
            section:!!sec,
            box:!!box,
            boxHTML:box?box.innerHTML.slice(0,2000):null,
            svgInBox:box?box.querySelectorAll('svg').length:0,
            lottieEls:box?box.querySelectorAll('[class*=lottie],svg,g,path').length:0,
            boxRect:box?(()=>{const r=box.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})():null,
            boxBg:box?getComputedStyle(box).backgroundColor:null,
            animations:document.getAnimations().length,
            nuxt:!!document.querySelector('#__nuxt'),
            bootstrap:!!window.__SITECLONER_LOCAL__
          }
        }""")
        print("RESULT",label,json.dumps({"http":resp.status if resp else None,"info":info,"requests":reqs,"responses":responses,"failed":[x for x in failed if "how_it_works" in x["url"] or "lottie" in x["url"].lower()],"errors":errors,"console":console[:30]},indent=2))
        await browser.close()

async def main():
    for label,url in URLS:
        try: await test(label,url)
        except Exception as e: print("RESULT",label,json.dumps({"fatal":repr(e)}))

asyncio.run(main())
