import asyncio, json
from playwright.async_api import async_playwright
URL="https://linearity-two.vercel.app/"
async def main():
    js=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        page=await b.new_page(viewport={"width":1760,"height":950})
        async def onresp(r):
            if "/_nuxt/" in r.url and r.url.endswith(".js"):
                try:
                    body=await r.body()
                    js.append({"url":r.url,"status":r.status,"bytes":len(body),"stub":body.startswith(b"/* unavailable captured script intentionally stubbed */")})
                except Exception:
                    pass
        page.on("response",lambda r: asyncio.create_task(onresp(r)))
        resp=await page.goto(URL,wait_until="domcontentloaded",timeout=90000)
        await page.wait_for_timeout(2500)
        h=await page.evaluate("document.documentElement.scrollHeight")
        for y in range(0,h,500):
            await page.evaluate("(y)=>scrollTo(0,y)",y)
            await page.wait_for_timeout(180)
        await page.wait_for_timeout(4000)
        await b.close()
    uniq={x["url"]:x for x in js}
    stubs=sorted([x for x in uniq.values() if x["stub"]],key=lambda x:x["url"])
    print("HTTP",resp.status if resp else None)
    print("TOTAL_NUXT_JS",len(uniq))
    print("STUB_REQUESTS",len(stubs))
    for x in stubs:
        print("STUB",x["url"].split("/_nuxt/",1)[1])
asyncio.run(main())
