(() => {
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
})();