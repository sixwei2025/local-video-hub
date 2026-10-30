/* Story recipes are progressively disclosed; existing production types stay intact. */
(()=>{
 let family='',query='',lastType='';
 const grid=document.querySelector('#styleGrid');
 const filters=document.createElement('div');filters.id='storyFilters';filters.hidden=true;grid.before(filters);
 const panel=document.createElement('section');panel.id='storyRecipe';panel.hidden=true;grid.after(panel);
 function applyFilter(){const t=findType(SEL.type);if(!t)return;grid.querySelectorAll('.sty').forEach(c=>{const p=t.presets.find(p=>p.id===c.dataset.s);c.hidden=!!(p&&!p.custom&&((family&&p.family&&p.family!==family)||(query&&!`${p.name} ${p.description} ${p.topics||''}`.includes(query))))});const visible=[...grid.querySelectorAll('.sty')].filter(c=>!c.hidden&&c.dataset.s!=='custom');document.querySelector('#storyCount').textContent=`${visible.length} 种`;if(visible.length&&!visible.some(c=>c.dataset.s===SEL.style)&&SEL.style!=='custom')pickStyle(visible[0].dataset.s)}
 function prompt(p){const f=document.querySelector('#jobForm');return p.prompt_template.replace('{{主题}}',f.prompt.value.trim()||'请填写主题').replace('{{材料}}','采用上方主题及用户提供的附件；未给出则按明确虚构故事创作').replace('{{画幅，默认9:16}}',document.querySelector('#fAspect').value||'9:16').replace('{{受众，默认普通成年人}}','普通成年人').replace('{{时长，默认60秒}}','60秒（用户已指定则以用户要求为准）')}
 async function copy(text){try{await navigator.clipboard.writeText(text);toast('制作指令已复制')}catch(e){toast('无法自动复制，请展开制作指令后手动复制',1)}}
 window.renderStoryRecipe=function(){const t=findType(SEL.type),p=t?.presets.find(p=>p.id===SEL.style),active=SEL.type==='storytelling';filters.hidden=!active;panel.hidden=!p?.prompt_template;grid.classList.toggle('story-grid',active);
 if(active&&lastType!==SEL.type){family='传统说演';query='';filters.innerHTML=`<div class="story-tools"><div class="story-families">${[...new Set(t.presets.map(x=>x.family).filter(Boolean))].map(f=>`<button type="button" data-family="${esc(f)}" class="${f===family?'on':''}">${esc(f)}</button>`).join('')}</div><label class="story-search"><input id="storySearch" aria-label="搜索故事风格" placeholder="搜索风格或用途"><span id="storyCount"></span></label></div>`;filters.querySelectorAll('[data-family]').forEach(b=>b.onclick=()=>{family=b.dataset.family;filters.querySelectorAll('[data-family]').forEach(x=>x.classList.toggle('on',x===b));applyFilter()});filters.querySelector('input').oninput=e=>{query=e.target.value.trim();applyFilter()};lastType=SEL.type;applyFilter()}
 else if(!active)lastType=SEL.type;
 if(active&&p?.family&&family!==p.family){family=p.family;filters.querySelectorAll("[data-family]").forEach(b=>b.classList.toggle("on",b.dataset.family===family));applyFilter()}
 if(!p?.prompt_template)return;
 panel.innerHTML=`<div class="recipe-actions"><span class="dim">配方已备 · 样片待验证</span><button type="button" class="btn" id="copyStoryPrompt">复制制作指令</button><a href="/api/story-style-kit" download>下载 Skill ↗</a></div><details><summary>制作说明与完整指令</summary><p>适合：${esc(p.topics)}</p><p>叙事：${esc(p.narrative)}。</p><p>画面：${esc(p.motion)}。</p><textarea readonly aria-label="完整制作指令">${esc(prompt(p))}</textarea><p>${esc(p.pitfall)}</p><p class="dim">实际成片取决于可用工具、素材与声音。</p></details>`;
 panel.querySelector('#copyStoryPrompt').onclick=()=>copy(prompt(p));
 };
 // Observer only follows card-list changes (not the recipe panel), including async initial loading.
 new MutationObserver(()=>window.renderStoryRecipe()).observe(grid,{childList:true});
 document.querySelector('#jobForm').prompt.addEventListener('input',()=>{const p=presetOf(SEL.type,SEL.style).P;if(p?.prompt_template&&panel.querySelector('textarea'))panel.querySelector('textarea').value=prompt(p)});
})();
