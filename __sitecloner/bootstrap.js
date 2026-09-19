(() => {
const im=(window.__SC_IM||[]).join("");
const data=JSON.parse((window.__SC_RT||[]).join(""));
const P=data.P||{}, N=data.N||{}, A=data.A||{};
const SOURCE=new Set(["www.linearity.io","linearity.io"]);
const rawValue=v=>String(v&&v.url?v.url:v);
const parse=v=>{try{return new URL(rawValue(v),location.href)}catch{return null}};
function mapResource(v){
  const raw=rawValue(v);
  const a=parse(v);
  if(!a)return raw;
  if(a.protocol==="data:"||a.protocol==="blob:")return a.href;
  if(a.origin===location.origin){
    if(a.pathname==="/.netlify/images"){
      try{
        const src=a.searchParams.get("url")||"";
        const u=new URL(decodeURIComponent(src),"https://assets.linearity.io");
        if(N[u.pathname])return N[u.pathname];
      }catch{}
    }
    if(P[a.pathname])return P[a.pathname];
    return a.pathname+a.search+a.hash;
  }
  if(SOURCE.has(a.hostname)){
    if(a.pathname==="/.netlify/images"){
      try{
        const src=a.searchParams.get("url")||"";
        const u=new URL(decodeURIComponent(src),"https://assets.linearity.io");
        if(N[u.pathname])return N[u.pathname];
      }catch{}
    }
    return P[a.pathname]||raw;
  }
  if(a.hostname==="assets.linearity.io"){
    return A[a.pathname]||N[a.pathname]||raw;
  }
  return raw;
}
const F=window.fetch.bind(window);
window.fetch=(input,init)=>F(mapResource(input),init);
const XO=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(method,url,...rest){return XO.call(this,method,mapResource(url),...rest)};
for(const [Ctor,name] of [[window.Worker,"Worker"],[window.SharedWorker,"SharedWorker"]]){
  try{if(Ctor)window[name]=function(url,opts){return new Ctor(mapResource(url),opts)}}catch{}
}
const setters=[[HTMLImageElement,"src"],[HTMLScriptElement,"src"],[HTMLLinkElement,"href"],[HTMLVideoElement,"src"],[HTMLAudioElement,"src"],[HTMLSourceElement,"src"],[HTMLIFrameElement,"src"]];
for(const [Ctor,prop] of setters){
  try{
    const d=Object.getOwnPropertyDescriptor(Ctor.prototype,prop);
    if(d&&d.set)Object.defineProperty(Ctor.prototype,prop,{...d,set(value){return d.set.call(this,mapResource(value))}})
  }catch{}
}
const SA=Element.prototype.setAttribute;
Element.prototype.setAttribute=function(name,value){
  if(["src","href","data"].includes(String(name).toLowerCase()))value=mapResource(value);
  return SA.call(this,name,value)
};
window.__SITECLONER_LOCAL__={pathMap:P,netlifyMap:N,assetMap:A};
const mapScript=document.createElement("script");
mapScript.type="importmap";
mapScript.textContent=im;
document.currentScript.before(mapScript);
})();