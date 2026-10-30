const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const api=(u,o)=>fetch(u,o).then(async r=>{if(!r.ok){let m=await r.text();try{const j=JSON.parse(m);m=typeof j.detail=="string"?j.detail:"提交的内容有误，请检查后再试"}catch(e){}throw new Error(m)}return r.json()});
const J=b=>({method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fsize=b=>b>1e9?(b/1e9).toFixed(1)+" GB":(b/1e6).toFixed(1)+" MB";
const PAGE=60;let CFG,STATS,STY,ITEMS=[],TOTAL=0,LOADING=false,SEQ=0;
const st={line:"",s:""};
function toast(msg,err){const t=document.createElement("div");t.className="toast"+(err?" err":"");t.textContent=msg;$("#toasts").appendChild(t);setTimeout(()=>t.remove(),err?6000:3500)}
function ask(html){return new Promise(res=>{$("#cText").innerHTML=html;$("#confirm").hidden=false;const done=v=>{$("#confirm").hidden=true;res(v)};$("#cYes").onclick=()=>done(true);$("#cNo").onclick=()=>done(false)})}
async function busy(btn,text,fn){const o=btn.textContent;btn.classList.add("loading");btn.disabled=true;btn.textContent=text;try{return await fn()}finally{btn.classList.remove("loading");btn.disabled=false;btn.textContent=o}}
const isDemo=()=>document.body.classList.contains("demo");
function setDemo(v){document.body.classList.toggle("demo",v);localStorage.setItem("hub-demo",v?"1":"0");$("#demoToggle").checked=v}
$("#demoToggle").onchange=e=>{setDemo(e.target.checked);toast(e.target.checked?"已切到演示模式：内部信息已隐藏":"已切到管理模式：显示完整信息")};
setDemo(localStorage.getItem("hub-demo")!=="0");
const lineOf=id=>CFG.lines.find(l=>l.id==id)||{name:"未归类",color:"#777"};
const findType=id=>STY.types.find(x=>x.id==id);const presetOf=(t,s)=>{const T=findType(t);return{T,P:T&&T.presets.find(x=>x.id==s)}};
const fmtD=s=>s?`${Math.floor(s/60)}:${String(Math.round(s%60)).padStart(2,"0")}`:"";
async function init(){[CFG,STY]=await Promise.all([api("/api/config"),api("/api/styles")]);
 STY.types.filter(t=>isHotTalk(t.id)).forEach(t=>t.name="热点口播");
 $("#genLine").innerHTML=CFG.lines.filter(l=>l.id!="other").map(l=>`<option value="${l.id}">${esc(l.name)}</option>`).join("");
 $("#styleSel").innerHTML=`<option value="">全部风格</option>`+STY.types.map(t=>`<optgroup label="${esc(t.name)}">`+t.presets.filter(p=>!p.custom).map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join("")+`</optgroup>`).join("")+`<option value="none">未识别</option>`;
 await loadOutDirs();await renderTypesMem();await loadStats();restoreCreationDraft();loadTags();route();window.onhashchange=route}
function route(){const [h0,qs]=location.hash.slice(1).split("?");const t=["gen","pub"].includes(h0)?h0:"lib";
 if(t=="gen"&&qs){const q=new URLSearchParams(qs);setTimeout(()=>sameStyle(q.get("t"),q.get("s"),q.get("topic")),0);history.replaceState(null,"","#gen")}$$(".mainnav a").forEach(a=>a.classList.toggle("on",a.dataset.tab==t));
 ["lib","gen","pub"].forEach(x=>$("#tab-"+x).hidden=x!=t);$(".newbtn").hidden=t=="gen";if(t=="lib")loadWorks(true);else if(t=="gen")loadJobs();else{loadReady();loadPubs()}}
/* 待办计数 */
async function loadTodo(){const T=await api("/api/todo");renderHero(T);
 $("#todo").innerHTML=[...(T.failed?[["failed","失败","#lib?failed"]]:[]),["making","制作中","#gen"],["confirm","待确认","#lib?confirm"],["ready","待发布","#pub"]].map(([k,n,h])=>`<a class="td ${k} ${T[k]?"has":""}" data-h="${h}"><b>${T[k]}</b>${n}</a>`).join("")+`<span class="tdx">已导出 ${T.exported||0} · 已发布 ${T.published} · 作品 ${T.works}</span>`;
 $$("#todo .td").forEach(a=>a.onclick=()=>{const[h,s]=a.dataset.h.split("?");if(s){setState(s);if(location.hash!="#lib")location.hash="#lib"}else location.hash=h});return T}
async function loadStats(){STATS=await api("/api/stats");const T=STATS.top;loadTodo();
 $("#scanInfo").textContent=STATS.scanned_at?`上次扫描 ${STATS.scanned_at}`:"正在扫描…";
 $("#lineList").innerHTML=`<li data-l="" class="${st.line==""?"on":""}"><span class="dot" style="background:var(--cream)"></span>全部产线<span class="n">${T.works}</span></li>`+
  CFG.lines.map(l=>{const x=STATS.lines[l.id];if(!x&&l.id=="other")return"";return`<li data-l="${l.id}" class="${st.line==l.id?"on":""}"><span class="dot" style="background:${l.color}"></span>${esc(l.name)}<span class="n">${x?x.final:0}</span></li>`}).join("");
 $$("#lineList li").forEach(li=>li.onclick=()=>{st.line=li.dataset.l;$$("#lineList li").forEach(x=>x.classList.toggle("on",x==li));loadWorks(true)});
 if(!STATS.scanned_at)setTimeout(()=>{loadStats();loadWorks(true)},2000)}
async function loadTags(){const t=await api("/api/tags");$("#tagSel").innerHTML=`<option value="">全部标签</option>`+Object.keys(t).map(k=>`<option>${esc(k)}</option>`).join("")}
/* 作品管理 */
const SN={"":"全部",making:"制作中",failed:"失败",exported:"已导出",confirm:"待确认",ready:"待发布",published:"已发布",featured:"★ 精选",archived:"已归档"};
function setState(s){st.s=s;$$("#stateSeg button").forEach(x=>x.classList.toggle("on",x.dataset.s==s));loadWorks(true)}
function params(off){const s=st.s;return new URLSearchParams({line:st.line,state:["making","failed","confirm","ready","exported","published"].includes(s)?s:"",featured:s=="featured"?1:0,archived:s=="archived"?1:0,
 q:$("#q").value,tag:$("#tagSel").value,date_from:$("#df").value,date_to:$("#dt").value,style:$("#styleSel").value,aspect:$("#aspect").value,sort:$("#sort").value,offset:off,limit:PAGE})}
function renderChips(){const c=[];if(st.line)c.push(["line",lineOf(st.line).name]);if(st.s)c.push(["s",SN[st.s]]);if($("#q").value)c.push(["q","搜索："+$("#q").value]);
 [["aspect","画幅"],["styleSel","风格"],["tagSel","标签"],["df","从"],["dt","到"]].forEach(([id,n])=>{const e=$("#"+id);if(e.value)c.push([id,n+"："+(e.selectedOptions?e.selectedOptions[0].text:e.value)])});
 $("#chips").innerHTML=c.map(([k,t])=>`<span class="chip" data-k="${k}">${esc(t)} ✕</span>`).join("")+(c.length>1?`<a class="clear" href="#lib">一键清除</a>`:"");
 $$("#chips .chip").forEach(x=>x.onclick=()=>{clr(x.dataset.k);loadWorks(true)});const cl=$("#chips .clear");if(cl)cl.onclick=e=>{e.preventDefault();c.forEach(([k])=>clr(k));loadWorks(true)}}
function clr(k){if(k=="line"){st.line="";$$("#lineList li").forEach(x=>x.classList.toggle("on",!x.dataset.l))}else if(k=="s"){st.s="";$$("#stateSeg button").forEach(x=>x.classList.toggle("on",!x.dataset.s))}else $("#"+k).value=""}
async function loadWorks(reset){if(LOADING&&!reset)return;const seq=++SEQ;LOADING=true;
 if(reset){ITEMS=[];renderChips();$("#grid").innerHTML=Array(8).fill(`<div class="cardv"><div class="thumb"><div class="skel"></div></div><div class="info"><div class="t">&nbsp;</div></div></div>`).join("")}
 try{const r=await api("/api/works?"+params(ITEMS.length));if(seq!=SEQ)return;TOTAL=r.total;if(reset)$("#grid").innerHTML="";ITEMS=ITEMS.concat(r.items);
  $("#grid").insertAdjacentHTML("beforeend",r.items.map(cardH).join(""));
  if(!ITEMS.length)$("#grid").innerHTML=`<div class="empty">${st.s=="archived"?"归档里还空着":"没有找到符合条件的作品"}</div>`;
  $("#count").textContent=`共 ${TOTAL} 部作品`;$("#sentinel").textContent=ITEMS.length<TOTAL?"继续下滑加载更多…":(ITEMS.length>PAGE?"已经到底了":"");
  bindThumbs()}catch(e){toast("作品列表没加载出来，请稍后刷新",1)}finally{if(seq==SEQ)LOADING=false}}
function bindThumbs(){$$(".thumb img:not([data-b])").forEach(im=>{im.dataset.b=1;const f=()=>{im.classList.add("ld");im.previousElementSibling?.remove()};im.complete&&im.naturalWidth?f():im.onload=f;im.onerror=()=>im.previousElementSibling?.classList.remove("skel")})}
new IntersectionObserver(es=>{if(es[0].isIntersecting&&ITEMS.length&&ITEMS.length<TOTAL&&!$("#tab-lib").hidden)loadWorks(false)},{rootMargin:"600px"}).observe($("#sentinel"));
const gridClick=e=>{const p=e.target.closest("[data-publish-work]");if(p){e.stopPropagation();openQuickPublish(p.dataset.publishWork);return}const d=e.target.closest("[data-del]");if(d){e.stopPropagation();delWork(d.dataset.del);return}const c=e.target.closest(".cardv[data-w]");if(c)openWork(c.dataset.w)};$("#grid").onclick=gridClick;$("#readyGrid").onclick=gridClick;
function styleTag(i){const unk=!i.video_type||i.style_name=="未识别";return unk?"":`<span class="sty-tag">${esc(i.video_type_name)} · ${esc(i.style_name)}</span>`}
function cardH(w){const l=lineOf(w.line);return`<div class="cardv ${w.portrait?"pt":""}" data-w="${w.work_id}"><div class="thumb">${w.thumb_url?`<div class="skel"></div><img loading="lazy" decoding="async" src="${w.thumb_url}" alt="">`:`<div class="ph">制作中…</div>`}
<button class="cdel" data-del="${w.work_id}" title="删除（移到废纸篓）" aria-label="删除作品">删除</button><span class="st s-${w.state}">${w.state_name}</span>${w.featured?`<span class="feat">★ 精选</span>`:""}${w.duration?`<span class="dur">${fmtD(w.duration)} · ${w.portrait?"竖屏":"横屏"}</span>`:""}</div>
<div class="info"><div class="t" title="${esc(w.work_title)}">${esc(w.work_title)}</div><div class="d"><span class="ln" style="--c:${l.color}">${esc(l.name)}</span>${styleTag(w)}<span>${w.date}</span></div>${w.state=="making"&&w.stage?`<div class="stage">⏳ ${esc(w.stage)}</div>`:""}${w.id&&!["making","failed"].includes(w.state)&&!w.archived?`<div class="card-actions"><button class="btn card-publish" data-publish-work="${w.work_id}">发布到抖音 / 视频号 / 小红书 ↗</button></div>`:""}${w.state=="failed"?`<div class="failline">✗ ${esc(w.error||w.stage||"制作失败")}</div>`:""}${w.state=="confirm"&&(w.stage||"").startsWith("已退回")?`<div class="stage">↩ ${esc(w.stage)}</div>`:""}</div></div>`}
let qt;$("#q").oninput=()=>{clearTimeout(qt);qt=setTimeout(()=>loadWorks(true),250)};
["#tagSel","#df","#dt","#styleSel","#aspect","#sort"].forEach(s=>$(s).onchange=()=>loadWorks(true));
$$("#stateSeg button").forEach(b=>b.onclick=()=>setState(b.dataset.s));
$("#moreBtn").onclick=()=>{$("#morePanel").hidden=!$("#morePanel").hidden};
let refreshingSite=false;
async function refreshSite(){
 if(refreshingSite)return;refreshingSite=true;
 const buttons=[$("#topRefresh"),$("#rescan")],labels=buttons.map(b=>b.textContent);
 buttons.forEach(b=>{b.disabled=true;b.textContent="刷新中…";b.setAttribute("aria-busy","true")});
 try{await api("/api/rescan",{method:"POST"});await loadStats();await loadTodo();
 if(!$("#tab-lib").hidden)await loadWorks(true);
 if(!$("#tab-gen").hidden){lastJobsView="";await loadJobs()}
 if(!$("#tab-pub").hidden){await loadPubStatus(true);await loadReady();await loadPubs()}
 toast("片库与页面已刷新");
 }catch(e){toast("刷新失败："+e.message,1)}finally{buttons.forEach((b,i)=>{b.disabled=false;b.textContent=labels[i];b.removeAttribute("aria-busy")});refreshingSite=false}
}
$("#rescan").onclick=refreshSite;$("#topRefresh").onclick=refreshSite;
/* 详情：左播放，右编辑 */
function styleInfoHTML(P){if(!P)return"还没有识别出风格，可以在上方手动选择";return`<b>${esc(P.name)}</b> · ${esc(P.description)}<span class="adm"><br>源项目：<span class="path">${esc(P.source_project)}</span><br>渲染方法：${esc(P.render_method)}</span>`}
async function openWork(wid,vid){let r;try{r=await api("/api/work/"+wid)}catch(e){toast("作品没打开："+e.message,1);return}
 const w=r.work,vs=r.versions,i=vs.find(v=>v.id==vid)||vs.find(v=>v.is_selected)||vs[0];
 if(!i){$("#mbody").innerHTML=`<div class="making"><h3>${esc(w.work_title)}</h3><span class="st s-making inl">制作中</span><p>当前阶段：<b>${esc(w.stage||"排队中")}</b></p>
  ${w.check_errors.length?`<div class="errs"><b>核对没通过：</b><ul>${w.check_errors.map(e=>`<li>${esc(e)}</li>`).join("")}</ul></div>`:""}${w.error?`<div class="errs">${esc(w.error)}</div>`:""}
  <p class="dim">${w.state=="failed"?"制作失败，可以直接重试，原来的设置都会保留。":"成片、封面、标题、简介、话题齐了之后会自动进入「待确认」。"}</p>${w.state=="failed"&&w.job_id?`<button class="primary" id="wRetry">重试（不用重填）</button>`:""}</div>`;
  if($("#wRetry"))$("#wRetry").onclick=e=>busy(e.target,"排队中",async()=>{try{await api(`/api/jobs/${w.job_id}/retry`,{method:"POST"});toast("已重新排队");$("#mclose").onclick();loadStats();loadWorks(true)}catch(err){toast("没排上："+err.message,1)}});$("#modal").hidden=false;return}
 const reload=async(x)=>{loadStats();if(!$("#tab-lib").hidden)loadWorks(true);if(!$("#tab-pub").hidden)loadReady();openWork(wid,x||i.id)};
 const upd=async(b,msg)=>{try{await api("/api/work/"+wid,J(b));toast(msg);return true}catch(e){toast("没保存上："+e.message,1)}};
 $("#mbody").innerHTML=`<div class="preview-toolbar"><div><b>${esc(w.work_title)}</b><span>${vs.length>1?"正在预览一个版本 · 共 "+vs.length+" 个版本":"视频预览"}</span></div><div class="preview-actions"><button type="button" class="primary" id="previewPublish">发布到抖音 / 视频号 / 小红书</button><button type="button" class="btn danger" id="previewDelete">${vs.length>1?"删除当前版本":"删除这条视频"}</button></div></div><div class="detail"><div class="dl"><video src="/media/${i.id}" controls autoplay preload="metadata" class="${i.portrait?"pt":""}"></video>
  <div class="vers"><h4>版本（${vs.length}）</h4>${vs.map(v=>`<div class="ver ${v.id==i.id?"on":""}" data-v="${v.id}"><img loading="lazy" src="/thumb/${v.id}"><div><b>${esc(v.title)}</b><span>${v.date}${v.duration?" · "+fmtD(v.duration):""}</span>
  <span>${v.version_label?`<i class="vt">${esc(v.version_label)}</i>`:""}${v.is_latest?`<i class="vt">最新</i>`:""}${v.is_selected?`<i class="vt sel">已选定</i>`:""}${v.really_published?`<i class="vt">已发布</i>`:""}</span><span class="path adm">${esc(v.path)}</span></div>${vs.length>1?`<button class="vdel" data-vdel="${v.id}" title="只删这个版本">删除此版本</button>`:""}</div>`).join("")}</div></div>
 <div class="dr"><div class="row" style="margin-top:0"><span class="st s-${w.state} inl">${w.state_name}</span>${w.featured?`<span class="feat inl">★ 精选</span>`:""}${w.archived?`<span class="dim">已归档</span>`:""}<span class="dim">${esc(lineOf(w.line).name)}</span></div>
  <div class="producer-box"><span>出品方</span><b id="producerName">${esc(i.producer_bot||w.producer_bot||"未登记机器人")}</b><button class="btn sm" id="editProducer">${w.producer_bot?"修改归属":"登记出品方"}</button><div class="producer-editor" id="producerEditor" hidden><select id="producerInput" aria-label="选择制作机器人" disabled><option value="">正在加载机器人…</option></select><button class="btn sm" id="saveProducer">保存归属</button></div></div>
  <label class="fl">标题<input id="wTitle" value="${esc(w.work_title)}"></label>
  <label class="fl">简介（发布≤30字）<textarea id="wDesc" rows="3" maxlength="30" placeholder="发布时用的简介，最多30字">${esc(w.description)}</textarea></label>
  <label class="fl">话题（逗号分隔）<input id="wTopics" value="${esc(w.topics.join("，"))}"></label>
  <div class="fl">封面<img class="wcover" src="${w.origin=="bot"&&w.thumb_url.startsWith("/workcover")?w.thumb_url:`/cover/${i.id}?r=3x4`}" alt=""></div>
  <div class="row"><button class="btn" id="wSave">保存文案</button><span class="dim">改文案不会重出视频</span></div>
  <div class="acts">
   ${w.state=="confirm"?`<button class="primary" id="wRevw">审核：确认 / 退回</button>`:w.state=="ready"?`<button class="btn" id="wBack">退回待确认</button>`:""}
   <button class="primary" id="wPub">发布到抖音 / 视频号 / 小红书</button>
   <button class="btn" id="wSel" ${i.is_selected?"disabled":""}>${i.is_selected?"当前版本已选定":"选定这个版本"}</button>
   <button class="btn" id="wFeat">${w.featured?"取消精选":"★ 标为精选"}</button>
   <button class="btn" id="wSame">照这个样式做一条</button>
   <button class="btn danger" id="wDel">删除作品</button>
   <button class="btn ghostsm" id="wArc">${w.archived?"从归档恢复":"归档（废片）"}</button></div>
  <div class="sec"><h4>修改意见</h4><div class="revision-recipient">${w.producer_bot?`接收方：${esc(w.producer_bot)}`:w.responsible_bot?`修改负责人：${esc(w.responsible_bot)}（按类型分配，出品方待核实）`:"先登记出品方，才能分发给对应机器人"}</div><textarea id="wRev" rows="2" placeholder="例如：标题更口语一点；第 3 段配音放慢；封面换成竖版大字"></textarea><div class="row"><button class="btn" id="wRevGo">${w.producer_bot?"提交给出品方":w.responsible_bot?"提交给修改负责人":"保存修改意见"}</button><span class="dim">保存后显示领取状态，不代表机器人已开始处理</span><div id="revisionStatus" class="dim"></div></div></div>
  <div class="sec"><h4>类型 · 风格</h4><div class="row" style="margin-top:0"><select id="mType"><option value="">未识别</option>${STY.types.map(t=>`<option value="${t.id}" ${t.id==i.video_type?"selected":""}>${esc(t.name)}</option>`).join("")}</select><select id="mStyle"></select><button class="btn" id="mStySave">保存</button></div><div class="styinfo" id="mStyInfo"></div></div>
  <div class="sec" id="mAltSec"><h4>换个风格再做一版</h4><div class="row" style="margin:0 0 10px"><input id="mTopic" style="flex:1" value="${esc(w.work_title)}" placeholder="一句话说明主题"></div><div class="altgrid" id="mAlt"></div></div>
  <div class="sec"><h4>审核与发布记录</h4><div id="wHist" class="dim">读取中…</div></div>
  </div></div><div id="mPubForm"></div>`;
 $("#previewDelete").onclick=()=>delWork(wid,vs.length>1?i.id:undefined);
 loadHist(wid);if($("#wRevw"))$("#wRevw").onclick=()=>openReview(w,vs,i);
 $("#modal").hidden=false;
 $$(".ver").forEach(v=>v.onclick=e=>{if(e.target.closest("[data-vdel]"))return;openWork(wid,v.dataset.v)});
 $$("[data-vdel]").forEach(b=>b.onclick=e=>{e.stopPropagation();delWork(wid,b.dataset.vdel)});$("#wDel").onclick=()=>delWork(wid);
 $("#wSave").onclick=e=>busy(e.target,"保存中",async()=>{if(await upd({title:$("#wTitle").value,description:$("#wDesc").value,topics:$("#wTopics").value.split(/[,，\s]+/)},"文案已保存"))reload()});
 const b=(id,body,msg)=>{const e=$(id);if(e)e.onclick=()=>busy(e,"处理中",async()=>{if(await upd(body,msg))reload()})};
 $("#wSame").onclick=()=>{$("#mclose").onclick();sameStyle(i.video_type,i.style_id,w.work_title)};
 const receipt=async()=>{const el=$("#revisionStatus");if(!el||!el.isConnected)return;try{const r=await api(`/api/work/${wid}/revision_status`);if(!el.isConnected)return;el.innerHTML=r.items.map(j=>`<div style="margin-top:8px">${esc(j.revise_text||"")}<br><b>${esc(j.target_bot||"待指定出品方")}</b> · ${j.status=="done"?"已完成":j.status=="failed"?"失败："+esc(j.error||j.stage||""):j.received_at?"已领取 · "+esc(j.stage||"处理中"):j.target_bot?"等待领取":"意见已保存，尚未分配"}</div>`).join("")}catch(e){}};
 receipt();
 $("#editProducer").onclick=()=>{$("#producerEditor").hidden=!$("#producerEditor").hidden};
 const producerSelect=$("#producerInput"),producerSave=$("#saveProducer");producerSave.disabled=true;
 api("/api/producers").then(r=>{if(!producerSelect.isConnected)return;const current=i.producer_bot||w.producer_bot||"";const names=[...new Set(r.bots.map(b=>b.name))];producerSelect.innerHTML='<option value="">请选择制作机器人</option>'+names.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join("");producerSelect.value=current;producerSelect.disabled=false;producerSave.disabled=!producerSelect.value;producerSelect.onchange=()=>producerSave.disabled=!producerSelect.value}).catch(()=>{if(producerSelect.isConnected){producerSelect.innerHTML='<option value="">加载失败，请关闭预览后重试</option>';toast("机器人列表加载失败，请重新打开预览",1)}});
 $("#saveProducer").onclick=e=>busy(e.target,"保存中",async()=>{try{await api(`/api/work/${wid}`,J({producer_bot:$("#producerInput").value}));toast("已登记出品方，未领取的修改任务已定向分配");await openWork(wid,i.id)}catch(err){toast(err.message,1)}});
 $("#wRevGo").onclick=e=>busy(e.target,"保存中",async()=>{const t=$("#wRev").value.trim();if(!t){toast("先写一句要改什么",1);return}
  try{const j=await api(`/api/work/${wid}/revise`,J({text:t,version_id:i.id}));$("#wRev").value="";$("#revisionStatus").textContent=j.target_bot?`已进入${j.target_bot}的修改队列，等待领取`:"意见已保存：尚未指定机器人，请先登记出品方";toast(j.target_bot?"修改意见已排队，等待出品方领取":"意见已保存，待登记出品方");receipt();loadTodo()}catch(err){toast("没发出去："+err.message,1)}});
 b("#wOk",{state:"ready"},"已确认成片，进入「待发布」");b("#wBack",{state:"confirm"},"已退回待确认");b("#wSel",{selected_version_id:i.id},"已选定这个版本，卡片默认显示它");
 b("#wFeat",{featured:!w.featured},w.featured?"已取消精选":"已标为精选");b("#wArc",{archived:!w.archived},w.archived?"已从归档恢复":"已归档，原文件不受影响");
 const preparePub=async()=>{
  const changed={title:$("#wTitle").value,description:$("#wDesc").value,topics:$("#wTopics").value.split(/[,，\s]+/).filter(Boolean)};
  if(changed.title!==w.work_title||changed.description!==w.description||JSON.stringify(changed.topics)!==JSON.stringify(w.topics)){
   await api("/api/work/"+wid,J(changed));w.work_title=changed.title;w.description=changed.description;w.topics=changed.topics;
  }
  await openPubForm(i,w);
 };
 ["#wPub","#previewPublish"].forEach(id=>$(id).onclick=e=>busy(e.target,"准备中",async()=>{try{await preparePub()}catch(err){toast("发布信息未保存："+err.message,1)}}));
 const fillStyles=()=>{const T=findType($("#mType").value);$("#mStyle").innerHTML=`<option value="">未识别</option>`+(T?T.presets.filter(p=>!p.custom).map(p=>`<option value="${p.id}" ${p.id==i.style_id?"selected":""}>${esc(p.name)}</option>`).join(""):"");showInfo();fillAlt()};
 const showInfo=()=>{$("#mStyInfo").innerHTML=styleInfoHTML(presetOf($("#mType").value,$("#mStyle").value).P)};
 const fillAlt=()=>{const T=findType($("#mType").value);const alts=T?T.presets.filter(p=>!p.custom&&p.id!=$("#mStyle").value):[];$("#mAltSec").hidden=!alts.length;
  $("#mAlt").innerHTML=alts.map(p=>`<div class="alt" data-s="${p.id}" title="${esc(p.description)}"><div style="background-image:url('/stylethumb/${p.id}')"></div><span>${esc(p.name)}</span></div>`).join("");
  $$(".alt").forEach(a=>a.onclick=async()=>{const p=presetOf($("#mType").value,a.dataset.s).P;const topic=$("#mTopic").value.trim();if(!topic){toast("请先写一句主题",1);$("#mTopic").focus();return}
   if(!await ask(`用「<b>${esc(p.name)}</b>」重新做一版？<br><span class="dim">主题：${esc(topic)} · 会加入生成队列，原片不受影响</span>`))return;
   try{await api("/api/rerender",J({video_id:i.id,video_type:$("#mType").value,style_id:a.dataset.s,prompt:topic}));toast(`已开始生成：${p.name}`);loadTodo()}catch(e){toast("没加进去："+e.message,1)}})};
 $("#mType").onchange=fillStyles;$("#mStyle").onchange=()=>{showInfo();fillAlt()};fillStyles();
 $("#mStySave").onclick=e=>busy(e.target,"保存中",async()=>{try{await api("/api/videos/"+i.id,J({status:i.status,tags:i.tags,note:i.note,video_type:$("#mType").value,style_id:$("#mStyle").value}));toast("类型·风格已保存");reload()}catch(err){toast("没保存上："+err.message,1)}})}
$("#mclose").onclick=()=>{$("#modal").hidden=true;$("#mbody").innerHTML=""};
$("#modal").onclick=e=>{if(e.target.id=="modal")$("#mclose").onclick()};
document.onkeydown=e=>{if(e.key=="Escape"){if(!$("#confirm").hidden)$("#cNo").click();else if(!$("#modal").hidden)$("#mclose").onclick()}};
/* 发布页：待发布作品 */
async function loadReady(){const r=await api("/api/works?state=ready&limit=200");$("#readyInfo").textContent=`${r.total} 部`;
 $("#readyGrid").innerHTML=r.items.map(cardH).join("")||`<div class="empty">还没有待发布的作品 · 在作品里点「确认成片」就会出现在这里</div>`;bindThumbs()}
/* 发布 */
async function openPubForm(i){let f;try{f=await api("/api/publish/prefill/"+i.id)}catch(e){toast("发布信息没准备好："+e.message,1);return}
 $("#mPubForm").innerHTML=`<div class="sec"><h4>发布</h4><div class="pubform">
 <div><img src="/cover/${i.id}?r=3x4&t=${Date.now()}" alt="封面"><div class="dim" style="margin-top:4px">封面 3:4（视频第一帧）</div><input id="pCover" class="adm" value="${esc(f.cover)}" style="width:100%;margin-top:6px;font-size:11px"></div>
 <div><div class="fl">平台<div class="plat">${f.platforms.map(p=>`<label class="${p.ok?"":"off"}"><input type="checkbox" value="${p.id}" ${p.ok?"checked":"disabled"}> ${p.name}<small>${p.ok?(isDemo()?"可以发布":esc(p.busy||p.mode)):"暂不可用："+esc(p.reason)}</small></label>`).join("")}</div></div>
 <label class="fl">标题（抖音≤30 / 小红书≤20）<input id="pTitle" value="${esc(f.title)}" maxlength="30"></label>
 <label class="fl">短标题（视频号，最多 16 字，不要标点）<input id="pShort" value="${esc(f.short_title)}" maxlength="16"></label>
 <label class="fl">简介（各平台≤30字）<textarea id="pDesc" rows="3" maxlength="30">${esc(f.desc)}</textarea></label>
 <label class="fl">视频号账号<select id="pAcct">${(f.accounts||[]).map(a=>`<option value="${esc(a.account)}" ${a.account==f.account?"selected":""}>${esc(a.account)}（${esc(a.desc)}）${a.ok?"":" · 需扫码/未就绪"}</option>`).join("")}</select></label>
 <label class="fl">话题（用逗号分隔）<input id="pTopics" value="${esc(f.topics.join("，"))}"></label>
 <label class="fl" style="flex-direction:row;align-items:center;gap:8px"><input type="checkbox" id="pAI" checked style="accent-color:var(--red)"> 抖音：声明「内容由AI生成」</label>
 <button class="primary" id="pGo">加入发布队列</button><div class="dim" style="margin-top:6px">加入后不会立刻发出，确认无误再正式发布。</div></div></div></div>`;
 $("#pGo").onclick=e=>busy(e.target,"提交中",async()=>{const plats=$$(".plat input:checked").map(x=>x.value);if(!plats.length){toast("请至少选一个平台",1);return}
  try{const r=await api("/api/publish",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({video_id:i.id,platforms:plats,title:$("#pTitle").value,short_title:$("#pShort").value,desc:$("#pDesc").value,topics:$("#pTopics").value.split(/[,，\s]+/),cover:$("#pCover").value,cover_h:f.cover_h,ai_declare:$("#pAI").checked,account:($("#pAcct")||{}).value||f.account})});
  toast(`已加入发布队列（${r.items.length} 个平台），等待确认后发布`);loadPubs()}catch(err){toast("没加进去："+err.message,1)}});
 loadTodo();$("#mPubForm").scrollIntoView({behavior:"smooth"})}
const PST={pending:"待发出",running:"发布中",done:"已发布",failed:"没发出去"};
const PN={douyin:"抖音",channels:"视频号",xhs:"小红书"};
const platLabel=j=>(PN[j.platform]||j.platform)+(j.platform==="channels"&&j.account?"·"+esc(j.account):(j.platform==="xhs"?"·袁六伟":""));
async function loadPubs(){const r=await api("/api/publish");$("#pubInfo").innerHTML=`共 ${r.items.length} 条<span class="adm"> · pub.py list / dryrun / run --approved</span>`;
 $("#pubList").innerHTML=r.items.length?r.items.map(j=>`<div class="job"><div class="h"><span class="pill ${j.status}">${PST[j.status]}</span><b>${platLabel(j)}</b><span class="publish-time">${esc(j.created_at.replace("T"," ").slice(0,16))}</span></div>
 <div class="p">${esc(j.title||j.short_title)}</div>${j.result_url?`<a href="${esc(j.result_url)}" target="_blank">查看作品</a>`:""}<div class="dim adm">${esc(j.video_path)}${j.last_dryrun?" · 演练："+esc(j.last_dryrun.tail):""}${j.error?" · "+esc(j.error):""}</div></div>`).join(""):`<div class="empty">发布队列是空的</div>`}
setInterval(()=>{if(location.hash=="#pub")loadPubs()},5000);

/* 参考视频 */
const fmtDur=s=>isFinite(s)?`${Math.floor(s/60)}:${String(Math.round(s%60)).padStart(2,"0")}`:"--:--";
const LIBREF=new Map();
function vcard(src,name,onrm){const d=document.createElement("div");d.className="vcard";d.innerHTML=`<video src="${src}" preload="none" controls></video><div class="vm"><b title="${esc(name)}">${esc(name)}</b><span class="dur">读取中</span></div>${onrm?`<button type="button" class="rm">移除</button>`:""}`;
 const v=d.querySelector("video");v.onloadedmetadata=()=>d.querySelector(".dur").textContent="时长 "+fmtDur(v.duration);v.onerror=()=>d.querySelector(".dur").textContent="浏览器无法预览";
 if(onrm)d.querySelector(".rm").onclick=onrm;return d}
function renderRefVideos(){const box=$("#refVidPrev");box.innerHTML="";
 [...$("#refVideos").files].forEach(f=>{const mb=f.size/1048576;box.appendChild(vcard(URL.createObjectURL(f),`${f.name} · ${mb.toFixed(0)}MB`))});
 LIBREF.forEach((it,id)=>box.appendChild(vcard(`/media/${id}`,"作品库："+it.title,()=>{LIBREF.delete(id);$("#refLibIds").value=[...LIBREF.keys()].join(",");renderRefVideos()})));
 $("#refUrls").value.split(/\s+/).filter(Boolean).forEach(u=>{const d=document.createElement("div");d.className="vcard url";d.textContent=u;box.appendChild(d)})}
$("#refVideos").onchange=e=>{const big=[...e.target.files].filter(f=>f.size>800*1048576);if(big.length){toast(`「${big[0].name}」超过 800MB，请压缩后再传`,1);e.target.value=""}
 const badext=[...e.target.files].filter(f=>!/\.(mp4|mov|webm|m4v)$/i.test(f.name));if(badext.length){toast("参考视频只支持 mp4 / mov / webm",1);e.target.value=""}renderRefVideos()};
$("#refUrls").oninput=()=>{clearTimeout(window._ut);window._ut=setTimeout(renderRefVideos,400)};
$$(".reftabs button").forEach(b=>b.onclick=()=>{$$(".reftabs button").forEach(x=>x.classList.toggle("on",x==b));$$("[data-rp]").forEach(p=>p.hidden=p.dataset.rp!=b.dataset.rt);if(b.dataset.rt=="lib")searchLib()});
async function searchLib(){const r=await api("/api/works?"+new URLSearchParams({q:$("#libPick").value,limit:20}));
 $("#libRes").innerHTML=r.items.map(i=>`<div data-id="${i.id}"><img loading="lazy" src="/thumb/${i.id}">${esc(i.work_title)}</div>`).join("")||`<div>没有找到</div>`;
 $$("#libRes div[data-id]").forEach(d=>d.onclick=()=>{const it=r.items.find(x=>x.id==d.dataset.id);it.title=it.work_title;LIBREF.set(it.id,it);$("#refLibIds").value=[...LIBREF.keys()].join(",");renderRefVideos();toast("已选为参考："+it.title)})}
$("#libPick").oninput=()=>{clearTimeout(window._lt);window._lt=setTimeout(searchLib,250)};

/* 创作 */
/* 创作 */
let SEL={type:"",style:""};
async function renderTypesMem(){try{SAMPLES=await api("/api/style_samples")}catch(e){}renderTypes();
 if(MEM.type&&findType(MEM.type)){pickType(MEM.type);if(MEM.style&&findType(MEM.type).presets.some(p=>p.id==MEM.style))pickStyle(MEM.style)}
 if(MEM.line&&MEM.type&&findType(MEM.type))$("#genLine").value=MEM.line;$("#fAspect").value=MEM.aspect||"";$("#fVoice").value=MEM.voice||"";if(MEM.aspect||MEM.voice)$("#moreSet").open=true;fillOut();
 ["#genLine","#fAspect","#fVoice"].forEach(s=>$(s).addEventListener("change",remember))}
const isHotTalk=id=>["hotnews","koubo"].includes(id);
const creationPresets=t=>isHotTalk(t.id)?STY.types.filter(x=>isHotTalk(x.id)).flatMap(x=>x.presets.filter(p=>!p.custom)).concat(t.presets.filter(p=>p.custom)):t.presets;
function renderTypes(){$("#typeBar").innerHTML=STY.types.filter(t=>!["koubo","collage"].includes(t.id)).map(t=>`<button type="button" class="stub" data-t="${t.id}">${esc(t.name)}<small>${t.presets.filter(p=>!p.custom).length} 种风格</small></button>`).join("");
 $$("#typeBar .stub").forEach(b=>b.onclick=()=>pickType(b.dataset.t));pickType(STY.types[0].id)}
let SAMPLES={};const MEM=JSON.parse(localStorage.getItem("hub-gen")||"{}");window.remember=()=>{localStorage.setItem("hub-gen",JSON.stringify({type:SEL.type,style:SEL.style,line:$("#genLine").value,aspect:$("#fAspect").value,voice:$("#fVoice").value}))};
function sameStyle(t,s,topic){location.hash="#gen";if(t&&findType(t)){pickType(t);if(s)pickStyle(s)}const p=$("#jobForm").prompt;if(topic&&!p.value)p.value=`照「${topic}」的样式做一条：`;p.focus();toast("已选好同款样式，换成你的内容就行")}
function pickType(id){if(id==="collage")id="hotnews";SEL.type=id;$("#fType").value=id;$$("#typeBar .stub").forEach(b=>b.classList.toggle("on",b.dataset.t==id||(isHotTalk(id)&&b.dataset.t=="hotnews")));const t=findType(id);$("#styleHint").textContent=isHotTalk(id)?"热点解读与观点口播，选择适合内容的画面效果":t.description;
 $("#styleGrid").innerHTML=creationPresets(t).map(p=>`<div class="sty" data-s="${p.id}">${p.prompt_template?`<div class="story-card-mark"><span>${esc(p.family)}</span><strong>${esc(p.name)}</strong></div>`:p.custom?`<div class="im cu">＋</div>`:`<div class="im" style="background-image:url('/stylethumb/${p.id}')">${p.mine?`<span class="mine-tag">我的</span>`:""}</div>`}<b>${esc(p.name)}</b><i>${esc(p.description)}</i></div>`).join("");
 $$(".sty").forEach(c=>{c.tabIndex=0;c.setAttribute("role","button");c.setAttribute("aria-label","选择"+(c.querySelector("b")?.textContent||"风格"));
 c.onclick=e=>{if(e.target.closest(".style-preview")){e.stopPropagation();window.StyleModal?.open(c.dataset.s,c,{name:c.querySelector("b")?.textContent,onUse:()=>{pickStyle(c.dataset.s);toast("已选好风格")}});return}pickStyle(c.dataset.s)};
 c.onkeydown=e=>{if(e.target!==c)return;if(e.key==="Enter"||e.key===" "){e.preventDefault();pickStyle(c.dataset.s)}};
 const sv=SAMPLES[c.dataset.s];if(!sv)return;const im=c.querySelector(".im");im.insertAdjacentHTML("beforeend",`<button type="button" class="play style-preview">▶ 看效果</button>`);
  c.onmouseenter=()=>{if(!im.querySelector("video"))im.insertAdjacentHTML("beforeend",`<video src="/media/${sv}" muted autoplay loop playsinline></video>`)};c.onmouseleave=()=>im.querySelector("video")?.remove()});
 if(!t.presets.length)$("#styleGrid").innerHTML='<div class="empty">暂未添加画面风格，做好样片后再添加。</div>';

 const ln=(CFG.type_lines||{})[id];if(ln)$("#genLine").value=ln;pickStyle(t.presets[0]?.id||"");if(OUTS.by_type)fillOut();remember()}
function pickStyle(id){if(isHotTalk(SEL.type)&&id!=="custom"){const source=STY.types.find(t=>isHotTalk(t.id)&&t.presets.some(p=>p.id===id));if(source){SEL.type=source.id;$("#fType").value=source.id;const ln=(CFG.type_lines||{})[source.id];if(ln)$("#genLine").value=ln;if(OUTS.by_type)fillOut()}}SEL.style=id;$("#fStyle").value=id;$$(".sty").forEach(c=>c.classList.toggle("on",c.dataset.s==id));$("#customBox").hidden=id!="custom";if(window.remember)remember();updateCreationSummary();if(window.renderStoryRecipe)renderStoryRecipe()}
let OUTS={by_line:{},by_type:{}};async function loadOutDirs(){OUTS=await api("/api/output_dirs");fillOut()}
const shortDir=p=>(p||"").replace(/\/+$/,"").split("/").pop();
function fillOut(){const t=OUTS.by_type[SEL.type],o=[...(t?[t]:[]),...(OUTS.by_line[$("#genLine").value]||[])].filter((x,i,a)=>a.indexOf(x)==i);
 $("#outList").innerHTML=o.map(d=>`<option value="${esc(d)}">`).join("");if(o[0])$("#genOut").value=o[0];showShort()}
function showShort(){$("#genOutShort").innerHTML=`📁 ${esc(shortDir($("#genOut").value))} <a href="#" id="chOut">更改</a>`;$("#chOut").onclick=e=>{e.preventDefault();document.body.classList.remove("demo");$("#demoToggle").checked=false;$("#genOut").focus();toast("已切到管理模式，可以改保存位置")}}
$("#genLine").onchange=fillOut;$("#genOut").oninput=showShort;
$("#refs").onchange=e=>{$("#refPrev").innerHTML=[...e.target.files].map(f=>`<img src="${URL.createObjectURL(f)}">`).join("")};

/* 参考视频链接解析：调用 /api/resolve，成功显示预览并把本地 mp4 排进 ref_videos，失败给中文提示+上传兜底 */
window.RESOLVED_REFS = window.RESOLVED_REFS || [];
async function resolveRefs(){
  const lines=($("#refUrls").value||"").split(/\n+/).map(s=>s.trim()).filter(Boolean);
  const out=$("#resolveOut"); if(!lines.length){out.innerHTML='<div class="dim">先在上面粘贴链接或分享文案</div>';return;}
  window.RESOLVED_REFS=[]; out.innerHTML="";
  for(const line of lines){
    const card=document.createElement("div"); card.className="vcard"; card.innerHTML='<div class="dim">解析中… '+esc(line.slice(0,40))+'</div>'; out.appendChild(card);
    try{
      const r=await fetch("/api/resolve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:line})});
      const d=await r.json();
      if(d.ok&&d.preview){
        const mb=(d.duration!=null)?`${Math.round(d.duration)}s`:"";
        card.innerHTML=`<video src="${d.preview}" controls preload="none" style="max-width:100%;max-height:220px"></video>`+
          `<div>${esc(d.title||"参考视频")}${mb?` · ${mb}`:""}${d.author?` · ${esc(d.author)}`:""}<span class="dim"> · ${esc(d.platform||"")} ✓</span></div>`;
        try{const b=await (await fetch(d.preview)).blob();
          window.RESOLVED_REFS.push(new File([b],(d.path||"ref.mp4").split("/").pop(),{type:"video/mp4"}));}catch(e){}
      }else{
        const msg=d.message||d.error||"无法解析该链接";
        card.innerHTML=`<div style="color:#c0392b">✗ ${esc(msg)}</div>`+
          (d.need_upload?`<div class="dim">请切到「上传视频」把本地文件拖进来。</div>`:"");
      }
    }catch(err){card.innerHTML=`<div style="color:#c0392b">✗ 解析失败：${esc(err.message||err)}</div>`;}
  }
}
const _rb=$("#resolveBtn"); if(_rb) _rb.onclick=()=>busy(_rb,"解析中",resolveRefs);
$("#jobForm").onsubmit=e=>{e.preventDefault();const f=e.target;busy($("#jobGo"),"提交中",async()=>{try{const _fd=new FormData(f);(window.RESOLVED_REFS||[]).forEach(x=>_fd.append("ref_videos",x,x.name));if(SEL.style=="custom"){SRV.filter(x=>x.file).forEach(x=>_fd.append("style_ref_videos",x.file,x.name));_fd.set("style_ref_paths",SRV.filter(x=>x.path).map(x=>x.path).join("\n"))}await api("/api/jobs",{method:"POST",body:_fd});
 f.prompt.value="";f.style_custom_text.value="";$("#refVideos").value="";$("#refUrls").value="";window.RESOLVED_REFS=[];$("#resolveOut")&&($("#resolveOut").innerHTML="");SRV.length=0;renderSRV();LIBREF.clear();$("#refLibIds").value="";renderRefVideos();$("#refs").value="";$("#styleRefs")&&($("#styleRefs").value="");$("#refPrev").innerHTML="";$("#styleRefPrev")&&($("#styleRefPrev").innerHTML="");clearCreationDraft();toast("已开始生成，进度会在右侧自动更新");loadJobs();loadTodo()}catch(err){toast("没提交上："+err.message,1)}})};
const JST={pending:"排队中",running:"制作中",done:"已交付",failed:"没做成"};const fileUrl=p=>"/file?path="+encodeURIComponent(p);
let lastJobsView="";
async function loadJobs(){const r=await api("/api/jobs");const signature=JSON.stringify(r.items);if(signature===lastJobsView)return;lastJobsView=signature;const c={};r.items.forEach(j=>c[j.status]=(c[j.status]||0)+1);
 $("#jobsInfo").textContent=`共 ${r.items.length} 条 · `+Object.entries(JST).map(([k,v])=>`${v} ${c[k]||0}`).join(" · ");
 $("#jobList").innerHTML=r.items.length?r.items.map(j=>{const{T,P}=presetOf(j.video_type,j.style_id);const nm=j.style_id=="custom"?"自定义风格":(P?P.name:"");
  return`<div class="job"><div class="h"><span class="pill ${j.status}">${JST[j.status]||j.status}</span><b>${esc(lineOf(j.line).name)}</b><span class="publish-time">${esc(j.created_at.replace("T"," ").slice(0,16))}</span></div>
 <div class="p">${esc(j.topic||j.prompt)}</div>${(j.ref_videos||[]).length||(j.ref_video_urls||[]).length?`<div class="dim" style="margin:4px 0">参考视频 ${(j.ref_videos||[]).length+(j.ref_video_urls||[]).length} 条${(j.ref_video_urls||[]).length?" · 含链接":""}</div>`:""}${nm?`<div class="jstyle">${P&&!P.custom?`<img src="/stylethumb/${P.id}">`:""}<div>${esc(T?T.name:"")} · <b>${esc(nm)}</b>${j.style_custom_text?`<div>${esc(j.style_custom_text)}</div>`:""}</div></div>`:""}
 ${j.kind=="revise"?`<div class="dim">修改意见：${esc(j.revise_text||"")}</div>`:""}
 ${j.status=="running"||j.stage?`<div class="stage">当前阶段：<b>${esc((j.work&&j.work.stage)||j.stage||"排队中")}</b></div>`:""}
 ${(j.check_errors||[]).length?`<div class="errs">核对没通过：${j.check_errors.map(esc).join("；")}</div>`:""}
 <div class="dim adm">保存位置：${esc(j.output_dir)}</div>${j.error?`<div style="color:var(--red-hi);font-size:13px;margin-top:6px">${esc(j.error)}</div>`:""}
 ${(j.result_paths||[]).length?`<div class="res" style="margin-top:8px">${j.result_paths.map(p=>/\.(mp4|mov|m4v)$/i.test(p)?`<video src="${fileUrl(p)}" controls preload="metadata"></video>`:/\.(jpe?g|png|webp)$/i.test(p)?`<img src="${fileUrl(p)}">`:"").join("")}</div>`:""}
 ${j.target_bot||j.kind=="revise"?`<div class="revision-receipt">${j.target_bot?"接收方："+esc(j.target_bot):"待指定出品方"} · ${j.received_at?"已领取":j.status=="pending"?"尚未领取":esc(j.stage||j.status)}</div>`:""}${jobDeliveryHTML(j)}<div class="jacts">${j.work_id&&j.status=="done"?`<button class="primary sm" data-open="${j.work_id}">预览 · 修改内容</button><button class="btn sm" data-pub="${j.work_id}">准备发布</button>`:""}
 ${["done","failed"].includes(j.status)?`<button class="btn sm" data-retry="${j.id}">${j.status=="failed"?"重试（不用重填）":"重新生成"}</button>`:""}</div></div>`}).join(""):`<div class="empty">还没有创作任务</div>`;
 $$("#jobList [data-open]").forEach(b=>b.onclick=()=>openWork(b.dataset.open));$$("#jobList [data-pub]").forEach(b=>b.onclick=async()=>{await openWork(b.dataset.pub);$("#wPub")?$("#wPub").click():toast("先在作品里点「确认成片」，再准备发布")});
 $$("#jobList [data-retry]").forEach(b=>b.onclick=()=>busy(b,"排队中",async()=>{try{await api(`/api/jobs/${b.dataset.retry}/retry`,{method:"POST"});toast("已重新排队，原来的设置都保留了");loadJobs();loadTodo()}catch(e){toast("没排上："+e.message,1)}}))}
setInterval(()=>{if(location.hash=="#gen")loadJobs()},5000);setInterval(loadTodo,15000);
init().catch(()=>toast("页面初始化失败，请刷新重试",1));

/* ===== Phase 3：审核 ===== */
const EVN={review:"审核",export:"导出",publish:"发布"};
async function loadHist(wid){try{const r=await api(`/api/work/${wid}/history`);const ev=r.events.map(e=>{const v=e.value||{};const pn={douyin:"抖音",channels:"视频号",xhs:"小红书",manual:"手动"}[v.platform]||v.platform||"";
  return `<li><span>${esc(e.created_at.replace("T"," ").slice(0,16))}</span> <b>${esc(e.label||EVN[e.kind])}</b> ${e.kind=="review"&&v.reason?"· "+esc(v.reason):""}${pn?" · "+esc(pn):""}${v.url?` · <a href="${esc(v.url)}" target="_blank">作品链接</a>`:""}</li>`});
  const pj=r.publish_jobs.map(j=>`<li><span>${esc(j.created_at.replace("T"," ").slice(0,16))}</span> 发布队列 · ${PN[j.platform]||j.platform} · <b>${PST[j.status]}</b>${j.last_dryrun?` · 演练${(j.last_dryrun.fails||[]).length||j.last_dryrun.code?"未通过":"通过"}`:""}</li>`);
  $("#wHist").innerHTML=ev.length||pj.length?`<ul class="hist">${ev.join("")}${pj.join("")}</ul>`:"还没有记录"}catch(e){$("#wHist").textContent="记录没读出来"}}
function openReview(w,vs,cur){const others=vs.filter(v=>v.id!=cur.id);let B=others[0];
 const pane=(v,tag)=>`<div class="cmp"><div class="dim">${tag} · ${esc(v.version_label||v.title)} · ${v.date}${v.duration?" · "+fmtD(v.duration):""}${v.is_latest?" · 最新":""}</div><video src="/media/${v.id}" controls preload="metadata"></video><label class="pick"><input type="radio" name="rvPick" value="${v.id}" ${v.id==cur.id?"checked":""}> 用这个版本</label></div>`;
 $("#mPubForm").innerHTML=`<div class="sec review"><h4>审核成片</h4>
  ${B?`<div class="cmpwrap">${pane(cur,"A")}${pane(B,"B")}</div>${others.length>1?`<div class="row"><span class="dim">B 换成</span><select id="rvB">${others.map(v=>`<option value="${v.id}">${esc(v.version_label||v.title)} · ${v.date}</option>`).join("")}</select></div>`:""}`:`<div class="dim">只有一个版本，确认画面没问题即可。</div>`}
  <div class="checks">${["画面完整、没有穿帮","声音和字幕对得上","封面清楚好看","标题、简介、话题没错字"].map(t=>`<label><input type="checkbox" class="rvc" value="${t}"> ${t}</label>`).join("")}</div>
  <div class="row"><button class="primary" id="rvOk">确认成片 → 待发布</button></div>
  <label class="fl">要退回修改？写一句原因（Grokbot 会照着改）<textarea id="rvReason" rows="2" placeholder="例如：第 2 段字幕和配音对不上；封面字太小"></textarea></label>
  <div class="row"><button class="btn" id="rvBack">退回修改</button></div></div>`;
 if($("#rvB"))$("#rvB").onchange=e=>{B=vs.find(v=>v.id==e.target.value);openReview(w,vs,cur);$("#rvB").value=B.id};
 $("#rvOk").onclick=e=>busy(e.target,"提交中",async()=>{const checks=$$(".rvc:checked").map(x=>x.value);if(checks.length<4&&!await ask(`还有 ${4-checks.length} 项没勾，确定要确认成片吗？`))return;
  const vid=($$('input[name=rvPick]:checked')[0]||{}).value||cur.id;
  try{await api(`/api/work/${w.work_id}/review`,J({action:"ok",version_id:vid,checks}));toast("已确认成片，进入「待发布」");loadStats();if(!$("#tab-lib").hidden)loadWorks(true);openWork(w.work_id,vid)}catch(err){toast("没确认上："+err.message,1)}});
 $("#rvBack").onclick=e=>busy(e.target,"提交中",async()=>{const r=$("#rvReason").value.trim();if(!r){toast("退回请写一句原因",1);$("#rvReason").focus();return}
  try{await api(`/api/work/${w.work_id}/review`,J({action:"back",reason:r}));toast("已退回，修改任务已发给 Grokbot");loadStats();loadWorks(true);openWork(w.work_id,cur.id)}catch(err){toast("没退回上："+err.message,1)}});
 $("#mPubForm").scrollIntoView({behavior:"smooth"})}
/* ===== Phase 3：发布流程（选平台 → 确认封面文案 → 确认） ===== */
let PSTAT=null;async function loadPubStatus(force){if(!PSTAT||force)PSTAT=await api("/api/publish_status");return PSTAT}
function renderPubBar(S){const el=$("#pubBar");if(!el)return;el.innerHTML=S.platforms.map(p=>`<div class="pbx ${p.ok?"ok":"bad"}"><b>${p.name}</b> ${p.ok?"登录正常":"不可用"}<span>今日已发 ${S.today[p.id]||0}/${S.limit[p.id]||10}</span>${p.ok?"":`<i>${esc(p.reason)}</i>`}</div>`).join("")+`<button class="btn sm" id="pRe">重新检测</button>`;
 $("#pRe").onclick=e=>busy(e.target,"检测中",async()=>{renderPubBar(await loadPubStatus(true));toast("已重新检测登录状态")})}
const cnt=(s,n)=>`<span class="cnt ${[...s].length>n?"over":""}">${[...s].length}/${n}</span>`;
async function openQuickPublish(wid){await openWork(wid);$("#previewPublish")?.click()}
async function openPubForm(i,w){let f,S;try{[f,S]=await Promise.all([api("/api/publish/prefill/"+i.id),loadPubStatus(true)])}catch(e){toast("发布信息没准备好："+e.message,1);return}
 w=w||{};const desc=w.description||f.desc,tops=(w.topics&&w.topics.length?w.topics:f.topics);
 $("#mPubForm").innerHTML=`<div class="sec pubwiz"><h4>发布视频</h4>
 <p class="dim">视频、标题、简介和话题已经带入。选择平台后，点击下方「确认发布」正式发出。</p>
 <div class="step"><b>发布到</b><div class="plat">${f.platforms.map(p=>{const n=S.today[p.id]||0,lim=S.limit[p.id]||10,full=n>=lim;return`<label class="${p.ok&&!full?"":"off"}"><input type="checkbox" value="${p.id}" ${p.ok&&!full?"checked":"disabled"}> ${p.name}<small>${!p.ok?"需要处理："+esc(p.reason):full?`今日已达上限 ${lim} 条`:`今日已发 ${n}/${lim}`}</small></label>`}).join("")}</div></div>
 <div class="step"><div class="pfields">
 <label class="fl">标题（抖音≤30 / 小红书≤20） <span id="cT"></span><input id="pTitle" value="${esc(f.title)}"></label>
 <label class="fl">视频号短标题 <span id="cS"></span><input id="pShort" value="${esc(f.short_title)}"></label>
 <label class="fl">简介（各平台≤30字）<textarea id="pDesc" rows="3" maxlength="30">${esc(desc)}</textarea></label>
 <label class="fl">视频号账号<select id="pAcct">${(f.accounts||[]).map(a=>`<option value="${esc(a.account)}" ${a.account==f.account?"selected":""}>${esc(a.account)}（${esc(a.desc)}）${a.ok?"":" · 需扫码/未就绪"}</option>`).join("")}</select></label>
 <label class="fl">话题<input id="pTopics" value="${esc(tops.join("，"))}"></label>
 <label class="fl rowc"><input type="checkbox" id="pAI" checked> 抖音：声明「内容由AI生成」</label>
 <input id="pCover" type="hidden" value="${esc(f.cover)}"></div><div class="previews" id="pPrev"></div>
 <p class="dim">抖音使用作品封面；视频号当前使用视频首帧作为封面。</p></div>
 <div class="publish-submit"><button class="primary" id="pGo">确认发布</button><span class="dim" id="pActionHint">这是正式发布，进度会显示在发布页。</span></div></div>`;
 const cov=f.cover_url||`/cover/${i.id}?r=3x4`,covh=`/cover/${i.id}?r=4x3`;
 const prev=()=>{const T=$("#pTitle").value,Sh=$("#pShort").value,D=$("#pDesc").value,tp=$("#pTopics").value.split(/[,，\s]+/).filter(Boolean),pl=$$("#mPubForm .plat input:checked").map(x=>x.value);
  const bad=(pl.includes("douyin")&&(!T.trim()||[...T].length>30))||(pl.includes("channels")&&(!Sh.trim()||[...Sh].length>16||/[，。！？；：、“”《》（）,]/.test(Sh)||!D.trim()))||(pl.includes("xhs")&&(!T.trim()||[...T].length>20||!D.trim()));
  $("#cT").innerHTML=cnt(T, pl.includes("xhs")&&!pl.includes("douyin")?20:30);$("#cS").innerHTML=cnt(Sh,16);
  $("#pGo").disabled=!pl.length||bad;$("#pGo").textContent=pl.length?`确认发布到${pl.map(p=>PN[p]||p).join("和")}`:"请先选择平台";
  $("#pActionHint").textContent=bad?"请补全所选平台的标题和简介（≤30字）；视频号短标题≤16字无标点；小红书标题≤20字。":"点击后正式发布，各平台分别显示结果。";
  $("#pPrev").innerHTML=(pl.includes("douyin")?`<div class="phone dy"><div class="pt">抖音</div><div class="scr"><img src="${cov}"><div class="ov"><b>${esc(T)}</b><p>${esc(D)} ${tp.map(x=>"#"+esc(x)).join(" ")}</p></div></div></div>`:"")+(pl.includes("channels")?`<div class="phone ch"><div class="pt">视频号 · ${esc(($("#pAcct")||{}).value||"")} · 首帧封面</div><div class="scr wide"><img src="${covh}"></div><b class="sh">${esc(Sh)}</b><p>${esc(D)} ${tp.map(x=>"#"+esc(x)).join(" ")}</p></div>`:"")+(pl.includes("xhs")?`<div class="phone dy"><div class="pt">小红书 · 袁六伟</div><div class="scr"><img src="${cov}"><div class="ov"><b>${esc(T)}</b><p>${esc(D)} ${tp.map(x=>"#"+esc(x)).join(" ")}</p></div></div></div>`:"");
 };
 $$("#mPubForm input,#mPubForm textarea,#mPubForm select").forEach(x=>x.addEventListener("input",prev));prev();
 $("#pGo").onclick=e=>busy(e.target,"正在提交发布…",async()=>{const plats=$$("#mPubForm .plat input:checked").map(x=>x.value);if(!plats.length)return;
  try{const r=await api("/api/publish/start",J({approved:true,video_id:i.id,platforms:plats,title:$("#pTitle").value,short_title:$("#pShort").value,desc:$("#pDesc").value,topics:$("#pTopics").value.split(/[,，\s]+/),cover:$("#pCover").value,cover_h:f.cover_h,ai_declare:$("#pAI").checked,account:($("#pAcct")||{}).value||f.account}));
   toast(r.items.every(j=>j.status=="done")?"这条视频已在所选平台发布，未重复发送":"正在发布，请在发布页查看各平台结果");$("#mclose").onclick();location.hash="#pub";loadPubs();loadTodo();
  }catch(err){toast("未能开始发布："+err.message,1)}});
 $("#mPubForm").scrollIntoView({behavior:"smooth",block:"start"});
}
async function loadReady(){const r=await api("/api/works?state=ready,exported&limit=200");$("#readyInfo").textContent=`${r.total} 部`;renderPubBar(await loadPubStatus());
 $("#readyGrid").innerHTML=r.items.map(cardH).join("")||`<div class="empty">还没有待发布的作品 · 在作品里审核「确认成片」后会出现在这里</div>`;bindThumbs()}
async function loadPubs(){const r=await api("/api/publish");$("#pubInfo").innerHTML=`${r.items.length} 条记录`;
 $("#pubList").innerHTML=r.items.length?r.items.map(j=>{const d=j.last_dryrun,dok=d&&!(d.fails||[]).length&&!d.code;const txt=`${j.title}\n\n${j.desc||""} ${(j.topics||[]).map(t=>"#"+t).join(" ")}`;
  return`<div class="job" data-p="${j.id}"><div class="h"><span class="pill ${j.status}">${PST[j.status]}</span><b>${platLabel(j)}</b>${j.exported?'<span class="pill exp">已导出</span>':""}<span class="publish-time">${esc(j.created_at.replace("T"," ").slice(0,16))}</span></div>
 <div class="p">${esc(j.title||j.short_title||"未命名作品")}</div>
 ${j.dry_running?`<div class="stage">⏳ 正在检查发布准备…</div>`:d?`<div class="${dok?"okline":"failline"}">${dok?"✓ 发布准备检查通过":((d.fails||[]).join("、")+(d.tail||"")).includes("NEED_SCAN")?"需要重新扫码登录平台":"发布准备检查未通过"} · ${esc(d.at.replace("T"," ").slice(5,16))}${j.dry_shot?` · <a href="/api/publish/${j.id}/dryshot" target="_blank">看截图</a>`:""}</div>`:""}
 ${j.result_url?`<a href="${esc(j.result_url)}" target="_blank">查看作品</a>`:""}${j.error&&j.status!="done"?`<div class="failline">${String(j.error).includes("NEED_SCAN")?"请重新扫码登录后重试":"发布未完成，请查看详情后重试"}</div>`:""}<details class="publish-diagnostics"><summary>查看详情</summary><p>记录编号：${esc(j.id)}</p>${j.error?`<p>${esc(j.error)}</p>`:""}${d&&!dok?`<p>${esc((d.fails||[]).join("、")||d.tail||"检查未通过")}</p>`:""}</details>
 <div class="jacts">${["pending","failed"].includes(j.status)?`<button class="btn sm" data-dry="${j.id}" ${j.dry_running?"disabled":""}>演练</button>`:""}
  ${j.status!="done"?`<a class="btn sm" href="/download/${j.video_id}" data-exp="${j.id}" data-w="${j.work_id||""}" data-pl="${j.platform}" data-what="video">下载视频</a><a class="btn sm" href="/api/publish/${j.id}/cover" data-exp="${j.id}" data-w="${j.work_id||""}" data-pl="${j.platform}" data-what="cover">下载封面</a><button class="btn sm" data-copy="${esc(txt)}" data-exp="${j.id}" data-w="${j.work_id||""}" data-pl="${j.platform}" data-what="text">复制文案</button>`:""}
  ${j.status=="failed"?`<button class="btn sm" data-rt="${j.id}">重试</button>`:""}
  ${["pending","failed"].includes(j.status)?`<button class="primary sm" data-run="${j.id}" ${j.needs_verification?"disabled":""}>${j.needs_verification?"请先核对平台结果":j.approved_at&&j.status=="pending"?"等待发布中":"确认发布"}</button>`:""}${j.status=="running"?`<span class="stage">正在上传 / 等待平台确认…</span>`:""}</div></div>`}).join(""):`<div class="empty">发布队列是空的</div>`;
 $$("#pubList [data-run]").forEach(b=>b.onclick=()=>busy(b,"提交中",async()=>{try{await api(`/api/publish/${b.dataset.run}/run`,J({approved:true}));toast("已开始正式发布");loadPubs()}catch(e){toast(e.message,1)}}));
 $$("#pubList [data-dry]").forEach(b=>b.onclick=()=>busy(b,"演练中",async()=>{await api(`/api/publish/${b.dataset.dry}/dryrun`,{method:"POST"});toast("开始演练：只填表、截图，不会发出");setTimeout(loadPubs,800)}));
 $$("#pubList [data-rt]").forEach(b=>b.onclick=()=>busy(b,"重试中",async()=>{await api(`/api/publish/${b.dataset.rt}/retry`,{method:"POST"});toast("已重新排队");loadPubs()}));
 $$("#pubList [data-exp]").forEach(b=>b.addEventListener("click",async()=>{if(b.dataset.copy){await navigator.clipboard?.writeText(b.dataset.copy).catch(()=>{});toast("文案已复制")}
  if(b.dataset.w)try{await api(`/api/work/${b.dataset.w}/export`,J({platform:b.dataset.pl,what:[b.dataset.what],pub_id:b.dataset.exp}));loadTodo();loadReady()}catch(e){}}))}
setInterval(()=>{if(location.hash=="#pub")loadPubs()},4000);

/* ===== 手动删除：移到废纸篓 ===== */
async function delWork(wid,vid){let p;try{p=await api(`/api/work/${wid}/delete_preview?vid=${vid||""}`)}catch(e){toast("没读到要删的内容："+e.message,1);return}
 const scope=p.scope=="version"?`这个作品里的 <b>1 个版本</b>（共 ${p.total_versions} 个）`:`<b>整个作品</b>（${p.versions} 个版本）`;
 const ok=await ask(`<div class="delbox"><h4>删除「${esc(p.title)}」？</h4><p>将删除${scope}，下列 ${p.files.length} 个文件会<b>移到废纸篓</b>，需要时可以从废纸篓恢复。</p>
  <ul class="dfiles">${p.files.map(f=>`<li>${esc(isDemo()?f.split("/").pop():f)}</li>`).join("")||"<li>（没有文件，只删除记录）</li>"}</ul>${p.published?`<p class="warn">⚠ 这是已发布的作品，删除后平台上的作品不受影响。</p>`:""}</div>`);
 if(!ok)return;
 if(p.published&&!await ask(`<div class="delbox"><h4>再确认一次</h4><p>「${esc(p.title)}」<b>已经发布过</b>。确定把它的文件移到废纸篓吗？</p></div>`))return;
 try{const r=await api(`/api/work/${wid}/delete`,J({version_id:vid||"",confirm_published:!!p.published}));
  toast(r.failed.length?`已移到废纸篓 ${r.trashed} 个，${r.failed.length} 个没移成：${r.failed[0].reason}`:"已移到废纸篓",!!r.failed.length);
  if(r.whole){$("#mclose").onclick()}else await openWork(wid);if(r.cleanup_warning)toast("文件已删除，记录清理稍后重试",1);await loadStats();await loadTodo();lastJobsView="";if(!$("#tab-gen").hidden)loadJobs();if(!$("#tab-lib").hidden)await loadWorks(true);if(!$("#tab-pub").hidden)await loadReady()}catch(e){toast("没删成："+e.message,1)}}

/* ===== 幕布英雄区：实时数据总览（必须保留，见 docs/设计规范.md） ===== */
function renderHero(T){const el=$("#hstats");if(!el)return;const tot=Math.max(1,T.works);
 const items=[["works","作品",T.works,""],["making","制作中",T.making,"making"],["confirm","待确认",T.confirm,"confirm"],["ready","待发布",T.ready,"ready"],["published","已发布",T.published,"published"],...(T.failed?[["failed","失败",T.failed,"failed"]]:[])];
 el.innerHTML=items.map(([k,n,v,s])=>`<a class="hs hs-${k}" data-s="${s}" title="查看${n}"><b>${v}</b><span>${n}</span><i style="--p:${k=="works"?100:Math.round(v/tot*100)}%"></i></a>`).join("")+
  `<div class="hsep"></div><div class="hs sm"><b>${T.week_new??0}</b><span>本周新增</span></div><div class="hs sm"><b>${T.today_pub??0}</b><span>今日发布</span></div>`;
 el.querySelectorAll("a.hs").forEach(a=>a.onclick=()=>{const s=a.dataset.s;if(s=="making"){location.hash="#gen";return}if(s=="ready"){location.hash="#pub";return}if(location.hash.startsWith("#gen")||location.hash=="#pub")location.hash="#lib";setState(s)});
 if(STATS&&CFG){const L=CFG.lines.filter(l=>STATS.lines[l.id]);const sum=L.reduce((a,l)=>a+STATS.lines[l.id].final,0)||1;const n=CFG.lines.filter(l=>l.id!="other").length;
  $("#edition").textContent=`${["零","一","二","三","四","五","六","七","八","九","十"][n]||n}条产线 · 作品总览`;
  $("#linebar").innerHTML=`<div class="lb">${L.map(l=>`<span style="flex:${STATS.lines[l.id].final};background:${l.color}" title="${esc(l.name)} ${STATS.lines[l.id].final}"></span>`).join("")}</div><div class="lbl">${L.map(l=>`<span><i style="background:${l.color}"></i>${esc(l.name)} ${STATS.lines[l.id].final}</span>`).join("")}</div>`}}
const _route0=route;route=function(){_route0();const h=location.hash.split("?")[0];document.body.classList.toggle("home",!["#gen","#pub"].includes(h));document.body.classList.toggle("lite",["#gen","#pub"].includes(h))};

/* ---- 自定义风格：参考视频（文件 / 链接），可存为「我的风格」 ---- */
const SRV=[];
function renderSRV(){const L=$("#srvList");if(!L)return;L.innerHTML="";SRV.forEach((x,n)=>{const d=document.createElement("div");
 if(x.wait){d.className="srv-card wait";d.textContent=x.wait;L.appendChild(d);return}
 d.className="srv-card";d.innerHTML=`<video src="${x.url}#t=0.5" muted playsinline preload="metadata"></video><span class="d">…</span><button type="button" class="rm" title="移除">×</button><div class="m"><b title="${esc(x.name)}">${esc(x.name)}</b><span>${x.path?"链接":"本地"}</span></div>`;
 const v=d.querySelector("video");v.onloadedmetadata=()=>{d.querySelector(".d").textContent=fmtD(v.duration)||"—"};
 d.onmouseenter=()=>v.play().catch(()=>{});d.onmouseleave=()=>{v.pause()};d.querySelector(".rm").onclick=()=>{SRV.splice(n,1);renderSRV()};L.appendChild(d)})}
function addSRVFiles(fs){[...fs].forEach(f=>{if(!/\.(mp4|mov|webm|m4v)$/i.test(f.name)){toast("只支持 mp4 / mov / webm 视频："+f.name,1);return}SRV.push({file:f,name:f.name,url:URL.createObjectURL(f)})});renderSRV()}
(function(){const dz=$("#srvDrop");if(!dz)return;const fi=$("#srvFile");dz.onclick=()=>fi.click();fi.onchange=()=>{addSRVFiles(fi.files);fi.value=""};
 dz.ondragover=e=>{e.preventDefault();dz.classList.add("over")};dz.ondragleave=()=>dz.classList.remove("over");dz.ondrop=e=>{e.preventDefault();dz.classList.remove("over");addSRVFiles(e.dataTransfer.files)};
 const rb=$("#srvResolve");rb.onclick=()=>busy(rb,"解析中",async()=>{const u=$("#srvUrl").value.trim();if(!u){toast("先粘贴视频链接或分享文案",1);return}
  if(/channels\.weixin\.qq\.com|视频号|weixin\.qq\.com\/sph/i.test(u)){toast("视频号链接暂时解析不了，请把视频文件下载后拖进来上传",1);return}
  const w={wait:"解析中… "+u.slice(0,40)};SRV.push(w);renderSRV();
  try{const r=await fetch("/api/resolve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u})});const d=await r.json();SRV.splice(SRV.indexOf(w),1);
   if(d.ok&&d.path){SRV.push({path:d.path,name:d.title||d.path.split("/").pop(),url:d.preview});$("#srvUrl").value="";toast("已解析："+(d.platform||"链接"))}
   else toast((d.message||d.error||"无法解析该链接")+(d.need_upload?"，请改为上传视频文件":""),1)}catch(e){SRV.splice(SRV.indexOf(w),1);toast("解析失败："+e.message,1)}renderSRV()});
 const sb=$("#srvSave");sb.onclick=()=>busy(sb,"保存中",async()=>{const nm=$("#srvName").value.trim(),ok=SRV.filter(x=>!x.wait);if(!nm){toast("先给风格起个名字",1);return}if(!ok.length&&!$("#jobForm").style_custom_text.value.trim()){toast("填写风格描述，或添加参考视频",1);return}
  const fd=new FormData();fd.append("name",nm);fd.append("video_type",SEL.type);fd.append("description",$("#jobForm").style_custom_text.value||"");ok.filter(x=>x.file).forEach(x=>fd.append("style_ref_videos",x.file,x.name));fd.append("style_ref_paths",ok.filter(x=>x.path).map(x=>x.path).join("\n"));
  try{const st=await api("/api/my_styles",{method:"POST",body:fd});STY=await api("/api/styles");window.StyleModal&&StyleModal.refresh();const t=SEL.type;renderTypes();pickType(t);pickStyle(st.id);$("#srvName").value="";SRV.length=0;renderSRV();toast("已存为我的风格："+st.name)}catch(e){toast(e.message,1)}})})();

/* Creation usability: drafts, persistent action dock and truthful delivery cards. */
function updateCreationSummary(){const p=presetOf(SEL.type,SEL.style);const e=document.querySelector('#creationSummary');if(e)e.textContent=[p.T?.name,p.P?.name].filter(Boolean).join(' · ')||'选择视频效果'}
function saveCreationDraft(){const f=document.querySelector('#jobForm'),d={};for(const name of ['prompt','style_custom_text','ref_video_urls'])d[name]=f.elements.namedItem(name)?.value||'';d.library=[...LIBREF.values()];d.files=[...f.querySelectorAll('input[type=file]')].flatMap(e=>[...e.files].map(f=>f.name));d.saved=Date.now();try{localStorage.setItem('hub-creation-draft',JSON.stringify(d));document.querySelector('#draftStatus').textContent=d.files.length?'草稿已保存 · 刷新后需重新选择本地附件':'草稿已自动保存到本机'}catch(e){document.querySelector('#draftStatus').textContent='草稿未能保存，请先复制文案'} }
function restoreCreationDraft(){let d;try{d=JSON.parse(localStorage.getItem('hub-creation-draft')||'null')}catch(e){}if(!d)return;const f=document.querySelector('#jobForm');for(const n of ['prompt','style_custom_text','ref_video_urls'])if(f.elements.namedItem(n))f.elements.namedItem(n).value=d[n]||'';for(const it of d.library||[])LIBREF.set(it.id,it);document.querySelector('#refLibIds').value=[...LIBREF.keys()].join(',');renderRefVideos();document.querySelector('#draftStatus').textContent=d.files?.length?'草稿已恢复 · 请重新选择附件：'+d.files.join('、'):'已恢复上次未提交的草稿'}
function clearCreationDraft(){localStorage.removeItem('hub-creation-draft');document.querySelector('#draftStatus').textContent='内容仅保存在本机浏览器'}
document.querySelector('#jobForm').addEventListener('input',saveCreationDraft);document.querySelector('#jobForm').addEventListener('change',saveCreationDraft);
window.addEventListener('pagehide',()=>{if(document.querySelector('#jobForm').prompt.value||LIBREF.size)saveCreationDraft()});
document.querySelector('#clearDraft').onclick=async()=>{if(!await ask('清空这次填写的内容和参考材料？已生成的作品不会删除。'))return;const f=document.querySelector('#jobForm');for(const n of ['prompt','style_custom_text','ref_video_urls'])f.elements.namedItem(n).value='';f.querySelectorAll('input[type=file]').forEach(e=>e.value='');LIBREF.clear();document.querySelector('#refLibIds').value='';window.RESOLVED_REFS=[];SRV.length=0;renderSRV();renderRefVideos();for(const id of ['refPrev','resolveOut'])document.getElementById(id).innerHTML='';clearCreationDraft();toast('已清空，开始新的创作')};
function jobDeliveryHTML(j){if(j.status!=='done')return '';const w=j.work;const title=w?.work_title||w?.title||'';const desc=w?.description||'';let topics=w?.topics||[];if(typeof topics==='string'){try{topics=JSON.parse(topics)}catch(e){topics=[]}}const cover=!!(w?.cover_path||w?.thumb_url);const missing=[!title&&'标题',!desc&&'简介',!cover&&'封面',!topics.length&&'话题'].filter(Boolean);return `<div class="delivery"><div class="delivery-head">发布材料 <span class="dim">${w?(missing.length?'待补充：'+esc(missing.join('、')):'材料已齐，请审核内容'):'尚未关联作品，发布材料待补充'}</span></div>${title?`<b>${esc(title)}</b>`:''}${desc?`<p>${esc(desc)}</p>`:''}${cover&&w.thumb_url?`<img class="delivery-cover" src="${esc(w.thumb_url)}" alt="作品封面">`:''}${topics.length?`<div class="dim">${topics.map(t=>'#'+esc(t)).join(' ')}</div>`:''}</div>`}
/* Media failures must offer a way out; do not auto-retry or force sound. */
function watchMedia(v){if(v.dataset.health)return;v.dataset.health='1';let timer,box;const note=(text,retry=false)=>{if(!box){box=document.createElement('div');box.className='media-health';box.setAttribute('role','status');v.insertAdjacentElement('afterend',box)}box.replaceChildren();const t=document.createElement('span');t.textContent=text;box.append(t);if(retry){const b=document.createElement('button');b.type='button';b.textContent='重新加载';b.onclick=()=>{v.load();v.play().catch(()=>note('已重新加载，点击播放器开始播放'))};box.append(b)}};const clear=()=>{clearTimeout(timer);box?.remove();box=null};v.addEventListener('error',()=>{clearTimeout(timer);note(v.error?.code===4?'视频格式不支持或文件不可用':v.error?.code===3?'视频解码失败':'视频加载失败，请检查文件或重试',true)});v.addEventListener('waiting',()=>{clearTimeout(timer);timer=setTimeout(()=>note('加载时间较长，可以重新加载',true),12000)});v.addEventListener('playing',clear);v.addEventListener('loadeddata',clear);v.addEventListener('loadstart',()=>{clearTimeout(timer);timer=setTimeout(()=>{if(v.readyState<2)note('视频尚未加载完成，可以重试',true)},15000)});if(v.error)note('视频暂时无法播放，请重新加载',true)}
new MutationObserver(()=>document.querySelectorAll('#jobList video,#modal video,#smod video').forEach(watchMedia)).observe(document.body,{childList:true,subtree:true});

/* Remember the publishing record layout without reloading or changing jobs. */
function setPublishLayout(layout){
 layout=layout==="vertical"?"vertical":"horizontal";
 $("#pubList").dataset.layout=layout;
 $$("[data-pub-layout]").forEach(b=>{const on=b.dataset.pubLayout===layout;b.classList.toggle("on",on);b.setAttribute("aria-pressed",String(on))});
 try{localStorage.setItem("publish-record-layout",layout)}catch(e){}
}
$$("[data-pub-layout]").forEach(b=>b.onclick=()=>setPublishLayout(b.dataset.pubLayout));
try{setPublishLayout(localStorage.getItem("publish-record-layout"))}catch(e){setPublishLayout("horizontal")}
