/* 风格小样弹窗：从被点的卡片位置放大到屏幕中央（FLIP），关闭时反向缩回。生成页与 /showcase 共用。 */
(function(){
const E=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let INFO=null,ORIGIN=null,ONUSE=null,OPEN=false,CUR=null;
const RM=()=>matchMedia("(prefers-reduced-motion: reduce)").matches;
const root=document.createElement("div");root.id="smod";root.hidden=true;
root.innerHTML=`<div class="smod-bg"></div><div class="smod-panel" role="dialog" aria-modal="true" aria-label="风格小样">
 <button class="smod-x" aria-label="关闭">×</button>
 <div class="smod-stage"><video class="smod-v" controls loop playsinline preload="none"></video><div class="smod-empty" hidden><b>暂无小样</b><span>可上传参考视频</span></div>
  <button class="smod-snd" type="button">🔇 打开声音</button></div>
 <div class="smod-info"><p class="smod-kick"></p><h3 class="smod-name"></h3><span class="smod-rule"></span><p class="smod-feat"></p>
  <dl class="smod-dl"><dt>适合选题</dt><dd data-k="topics"></dd><dt>默认画幅</dt><dd data-k="aspect"></dd><dt>默认时长</dt><dd data-k="duration"></dd><dt>预计制作</dt><dd data-k="eta"></dd><dt class="smod-cv-t" hidden>封面 3:4</dt><dd class="smod-cv" hidden><img alt="封面样图 3:4" style="width:96px;aspect-ratio:3/4;object-fit:cover;border-radius:6px;display:block"></dd></dl>
  <button class="smod-use" type="button">用这个风格</button></div></div>`;
document.addEventListener("DOMContentLoaded",()=>document.body.appendChild(root));
if(document.readyState!="loading")document.body.appendChild(root);
const P=()=>root.querySelector(".smod-panel"),V=()=>root.querySelector(".smod-v");
async function info(){if(!INFO){try{INFO=await (await fetch("/api/style_info")).json()}catch(e){INFO={}}}return INFO}
function fill(s,fallbackName){const v=V();CUR=s;
 root.querySelector(".smod-kick").textContent=s?[s.type_name,s.mine?"我的风格":""].filter(Boolean).join(" · "):"自定义风格";
 root.querySelector(".smod-name").textContent=s?s.name:(fallbackName||"自定义风格");
 root.querySelector(".smod-feat").textContent=s?s.features:"写下风格描述，或上传一两条参考视频，我们照着它的感觉做。";
 root.querySelectorAll(".smod-dl dd[data-k]").forEach(d=>d.textContent=(s&&s[d.dataset.k])||"—");
 const cv=!!(s&&s.cover);root.querySelector(".smod-cv").hidden=!cv;root.querySelector(".smod-cv-t").hidden=!cv;if(cv)root.querySelector(".smod-cv img").src=s.cover;
 const has=!!(s&&s.sample);root.querySelector(".smod-empty").hidden=has;v.hidden=!has;root.querySelector(".smod-snd").hidden=!has;
 v.muted=false;v.volume=1;root.querySelector(".smod-snd").textContent="🔊 关闭声音";
 if(has){v.classList.toggle("pt",!!s.sample.portrait);if(v.getAttribute("src")!=s.sample.url){v.src=s.sample.url}v.play().catch(()=>{})}else{v.pause();v.removeAttribute("src");v.load()}}
function flip(from,reverse){const p=P();if(RM()||!from){p.style.transform="";return Promise.resolve()}
 const a=from.getBoundingClientRect(),b=p.getBoundingClientRect();
 const t=`translate(${a.left+a.width/2-(b.left+b.width/2)}px,${a.top+a.height/2-(b.top+b.height/2)}px) scale(${Math.max(a.width/b.width,.05)},${Math.max(a.height/b.height,.05)})`;
 const k=reverse?[{transform:"none",opacity:1},{transform:t,opacity:.2}]:[{transform:t,opacity:.2},{transform:"none",opacity:1}];
 return p.animate(k,{duration:reverse?300:360,easing:reverse?"cubic-bezier(.4,0,.6,1)":"cubic-bezier(.16,1,.3,1)",fill:"both"}).finished.then(a=>{a&&a.cancel&&a.cancel()}).catch(()=>{})}
async function open(sid,from,opts={}){const I=await info();ORIGIN=from||null;ONUSE=opts.onUse||null;
 root.querySelector(".smod-use").textContent=opts.useText||"用这个风格";
 fill(I[sid]||null,opts.name);
 if(OPEN){return}   // 已打开：直接切换内容
 OPEN=true;root.hidden=false;document.documentElement.classList.add("smod-on");
 requestAnimationFrame(()=>root.classList.add("show"));await flip(ORIGIN,false);root.querySelector(".smod-use").focus({preventScroll:true})}
async function close(){if(!OPEN)return;OPEN=false;root.classList.remove("show");
 const el=ORIGIN&&document.body.contains(ORIGIN)?ORIGIN:null;await flip(el,true);
 root.hidden=true;document.documentElement.classList.remove("smod-on");const v=V();v.pause();v.removeAttribute("src");v.load();P().getAnimations().forEach(a=>a.cancel())}
root.addEventListener("click",e=>{if(e.target.classList.contains("smod-bg")||e.target.classList.contains("smod-x"))close();
 if(e.target.classList.contains("smod-snd")){const v=V();v.muted=!v.muted;e.target.textContent=v.muted?"🔇 打开声音":"🔊 关闭声音";if(!v.muted)v.play().catch(()=>{})}
 if(e.target.classList.contains("smod-use")){const f=ONUSE,s=CUR;close();f&&f(s)}});
document.addEventListener("keydown",e=>{if(e.key=="Escape"&&OPEN){e.preventDefault();close()}});
window.StyleModal={open,close,refresh(){INFO=null},isOpen:()=>OPEN};
})();
