#!/usr/bin/env python3
"""生成/刷新 styles.json 的缩略图缓存（只读源项目，只往 ~/video-hub/cache/styles 写）。
用法：.venv/bin/python build_styles.py        # 按 styles.json 里每个 preset 的 thumbnail_source 生成 thumbnail
       .venv/bin/python build_styles.py --init # 用内置默认重新写 styles.json（会覆盖手改内容）"""
import json, os, subprocess, sys
from pathlib import Path
H = os.path.expanduser("~"); ROOT = Path(__file__).resolve().parent; OUT = ROOT / "cache/styles"
L = H + "/lab"; G = H + "/GrokBridge"; D = H + "/Desktop"
V2 = L + "/ainews-codex额度-v2"; V3 = L + "/ainews-codex额度-v3"
HAM = "huashu-art-motion（~/lab/skills/huashu-art-motion）：specs/镜*.json → 代码工程/render.py（Playwright 无头 Chrome 逐帧渲 HTML/JS）→ ffmpeg 拼接 → ov/compose.py 叠封面/角标/字幕 PNG + BGM"
def P(id, name, desc, src, method, thumb_src, ss=None, auto="script-with-spec", **kw):
    return dict(id=id, name=name, description=desc, source_project=src, render_method=method,
                thumbnail_source=thumb_src, thumbnail_seek=ss, thumbnail=f"cache/styles/{id}.jpg", automation=auto, **kw)
CUSTOM = {"id": "custom", "name": "自定义风格", "description": "自己写风格描述，可附风格参考图", "custom": True}
TYPES = [
 {"id": "psych", "name": "心理科普", "description": "心理学选题，竖屏短视频，克隆声配音", "presets": [
   P("psych-v3-short", "心理科普 v3 · 60 秒短版", "克隆声 1.25×、分镜插画、3:4 封面，一条龙出片",
     G + "/kepu/psych/v3", "SLUG=psyXX TITLE='…' bash ~/GrokBridge/kepu/psych/v3/run_ep.sh（配音→分镜→混音→封面→正片→质检→桌面）",
     D + "/心理学科普/视频作品/冷战为什么比吵架还伤人？一个婴儿实验给了答案.mp4", 3),
   P("psych-vibe", "Vibe 知识大赏", "Remotion 动态图文 + 克隆声，标题党式知识点（已发布多条）",
     L + "/vibe-信息论", "bash ~/lab/vibe_pipeline.sh <项目目录> <名字> <instruct>：tts_batch.py → timeline.py → npx remotion render Main → Cover34 封面；需复制一个 vibe-* 项目改 proj/src 文案", L + "/vibe-信息论/out/vibe-信息论-封面.jpg", auto="script-with-project-copy"),
 ]},
 {"id": "hotnews", "name": "热点新闻", "description": "AI/科技热点快评，横屏 16:9 约 30 秒", "presets": [
   P("hotnews-v3-vox-desk", "Vox 调查桌 · 剪报红笔（V3）", "牛皮纸桌面上铺剪报、截图，红笔圈画批注，镜头推拉追线索",
     V3, "V3：bash build.sh。素材 mat/gen.py 生成剪报 PNG（rects.json 定位）→ specs/镜01-08.json → 代码工程/render.py → ov/compose.py；QA 用 huashu-art-motion scripts/qa.py、deliver.py", V3 + "/out/k9.jpg"),
   P("hotnews-v2-a-vox", "A · Vox 调查桌（V2 样）", "V2 的剪报+红笔小样，V3 的前身，节奏更慢",
     V2, "V2 styles/run.sh：render.py --spec styles/A_vox.json（" + HAM + "）", V2 + "/styles/A_vox.jpg"),
   P("hotnews-v2-b-whiteboard", "B · 黑板手绘", "深色黑板粉笔手绘，边讲边画示意图和关键词",
     V2, "V2 styles/run.sh：render.py --spec styles/B_whiteboard.json（" + HAM + "）", V2 + "/styles/B_whiteboard.jpg"),
   P("hotnews-v2-c-keynote", "C · 发布会 UI", "苹果发布会式大字 + 产品界面卡片，干净科技感",
     V2, "V2 styles/run.sh：render.py --spec styles/C_keynote.json（" + HAM + "）", V2 + "/styles/C_keynote.jpg"),
   P("hotnews-v2-d-3b1b", "D · 3b1b 公式推导", "黑底数学动画风，数字/公式逐步推导讲清账",
     V2, "V2 styles/run.sh：render.py --spec styles/D_3b1b.json（" + HAM + "）", V2 + "/styles/D_3b1b.jpg"),
   P("hotnews-v2-ink-kinetic", "V2 成片 · 水墨动态字", "V2 正片：y1_kurzgesagt + y5_kinetic_type 片段，ink 主题，强调红 #C8102E，胶片质感",
     V2, "V2：bash build.sh（specs/镜*.json → " + HAM + "）", V2 + "/out/k9.jpg"),
 ]},
 {"id": "wenzhe", "name": "文哲", "description": "文学哲学，无旁白、烧录字幕阅读", "presets": [
   P("wenzhe-sisyphus", "文学哲学 · 西西弗斯模板", "无旁白无 BGM，烧录字幕慢读，名著意象画面",
     G + "/tutorial/wenxue-sisyphus", "bash ~/GrokBridge/tutorial/wenxue-sisyphus/run_chain.sh（proj/ 为工程，规格见 使用说明.md）", D + "/视频大杂烩/文学哲学-西西弗斯-样片-封面.jpg", auto="script-with-project-copy"),
 ]},
 {"id": "duanju", "name": "人物传记", "description": "人物传记叙事短视频", "presets": [
   P("duanju-biopic", "人物传记（雷军传记）", "TTS 旁白 + 分段画面 + 封面版，传记叙事",
     G + "/短剧/雷军传记", "~/GrokBridge/短剧/雷军传记/run.sh：tts.py → cover.py → build.py → check.py（lines.json 为台词）", G + "/短剧/雷军传记/雷军传记_封面版.mp4", 2, auto="script-with-project-copy"),
   P("duanju-wangmang-hypit", "王莽传记 · hypit 60s", "vibe 知识大赏 hypit 管线，60 秒人物传记（王莽）",
     G + "/短剧/王莽-vibe知识大赏/v8-hypit", "v8-hypit：film60 管线出 film60_ln.mp4 + cover_3x4；对标 vibe/hypit 知识大赏节奏",
     G + "/短剧/王莽-vibe知识大赏/v8-hypit/out/film60/film60_ln.mp4", 2, auto="script-with-project-copy"),
   P("duanju-shijianqiao-storystudio", "施剑翘 · story-studio 黑白纪实", "story-studio 黑白纪实人物传记，竖屏成片 + 3:4 封面",
     G + "/短剧/story-studio-施剑翘", "story-studio-施剑翘：images + audio → final_v4.mp4；COVER_3x4.png 作封面",
     G + "/短剧/story-studio-施剑翘/images/COVER_3x4.png", auto="script-with-project-copy"),
 ]},
 {"id": "map3d", "name": "3D 地图", "description": "战争史/地理 3D 地图动画", "presets": [
   P("map3d-war", "3D 地图 · 战争史", "卫星瓦片 3D 地形 + 行军箭头 + 口播配乐",
     D + "/3D地图视频-方法包", "bash ~/Desktop/3D地图视频-方法包/引擎/run.sh <episode>（episodes/<名>.json：compile→口播→配乐→封面→渲帧→编码）", D + "/3D 地图视频/战争史/昆阳之战-横封面4x3.jpg", auto="script-with-spec"),
 ]},
 {"id": "koubo", "name": "口播", "description": "真人口播配画面，竖屏 1080×1920", "presets": [
   P("koubo-a-news", "A · 新闻播报", "新闻台式版面，标题条 + 资料卡", G + "/口播/_styles", "bash ~/GrokBridge/口播/_styles/make_episode.sh <项目> A（只写 episode.json + segments.json + 配音时间轴）", D + "/口播风格小样/A_news.mp4", 3, auto="script-with-spec"),
   P("koubo-b-desk", "B · 桌面实拍感", "书桌俯拍质感，资料散落桌面", G + "/口播/_styles", "bash make_episode.sh <项目> B", D + "/口播风格小样/B_desk.mp4", 3, auto="script-with-spec"),
   P("koubo-c-collage", "C · 拼贴", "截图剪贴拼贴 + 关键词红字", G + "/口播/_styles", "bash make_episode.sh <项目> C", D + "/口播风格小样/C_collage.mp4", 3, auto="script-with-spec"),
   P("koubo-d-board", "D · 白板", "白板讲解版式，逐条板书", G + "/口播/_styles", "bash make_episode.sh <项目> D", D + "/口播风格小样/D_board.mp4", 3, auto="script-with-spec"),
 ]},
 {"id": "promo", "name": "宣传片", "description": "城市/品牌宣传片，16:9 24fps，克隆声", "presets": [
   P("promo-a-wuhan", "A · 武汉配方（默认）", "移轴微缩 × 钢笔淡彩 × 霓虹夜景", H + "/hx-promo/城市宣传片风格库", "见 风格注册表.md · A；Lemo 组合 tilt-shift + urban-sketch（~/hx-promo/lemo-opuscar）", D + "/汇芯宣传片/武汉城市宣传片_移轴微缩×钢笔淡彩×霓虹_克隆声_v3.mp4", 4, auto="manual-remotion"),
   P("promo-b-ukiyoe", "B · 浮世绘卷轴", "和纸底套色木版，手卷横移", H + "/hx-promo/城市宣传片风格库", "风格注册表.md · B；B_浮世绘卷轴_杭州/lemo", H + "/hx-promo/城市宣传片风格库/样片/杭州城市宣传片_浮世绘卷轴_克隆声_短样v1.mp4", 4, auto="manual-remotion"),
   P("promo-c-watercolor", "C · 水彩旅记", "棉纸水彩，旅行手账感", H + "/hx-promo/城市宣传片风格库", "风格注册表.md · C；C_水彩旅记_苏州/lemo", H + "/hx-promo/城市宣传片风格库/样片/苏州城市宣传片_水彩旅记_克隆声_短样v1.mp4", 4, auto="manual-remotion"),
   P("promo-d-stainedglass", "D · 彩玻灯窗", "彩色玻璃灯窗，山城夜色", H + "/hx-promo/城市宣传片风格库", "风格注册表.md · D；D_彩玻灯窗_重庆/lemo", H + "/hx-promo/城市宣传片风格库/样片/重庆城市宣传片_彩玻灯窗_克隆声_短样v1.mp4", 4, auto="manual-remotion"),
   P("promo-aerial", "电影航拍 · 一天时间线", "电影感航拍，按一天时间线推进", H + "/hx-promo/城市宣传片风格库/电影航拍", "电影航拍/配方.md", D + "/汇芯宣传片/武汉城市宣传片_一天时间线_电影航拍_v1.mp4", 6, auto="manual-remotion"),
 ]},
 {"id": "daihuo", "name": "带货", "description": "商品带货短视频", "presets": [
   P("daihuo-sample", "带货小样（2026-10-21）", "Remotion 图文带货：痛点大字 + 卖点卡 + 人物插画",
     G + "/带货小样-20261021", "Remotion 工程 ~/GrokBridge/带货小样-20261021（src/ + lines.txt 文案，npx remotion render）", G + "/带货小样-20261021/preview.jpg", auto="manual-remotion"),
 ]},
 {"id": "collage", "name": "拼贴风", "description": "剪报/截图拼贴类视觉", "presets": [
   P("collage-vox", "Vox 剪报拼贴", "同热点新闻 V3：剪报 + 红笔圈画", V3, "同 hotnews-v3-vox-desk（V3 build.sh）", V3 + "/out/k9.jpg"),
   P("collage-koubo-c", "口播拼贴（C）", "同口播 C：竖屏截图拼贴", G + "/口播/_styles", "bash make_episode.sh <项目> C", D + "/口播风格小样/C_collage.mp4", 3, auto="script-with-spec"),
 ]},
 {"id": "vibe", "name": "Vibe 知识大赏", "description": "andyhuo520/vibe-knowledge：44 套风格×六种母版；代码成片知识短片。源 ~/lab/vibe-knowledge", "presets": [
   P("vibe-gufeng", "东方 · 古风", "夜色赭黑的城门与人群剪影，朱红印章和金色数字，像翻开一本暗调的历史绘本 适合：历史事件 · 两难选择 · 古代制度。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/gufeng/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/gufeng/still.jpg", auto="recipe-with-skill"),
   P("vibe-starfield", "暗场概念 · 星空光点", "深蓝黑星空里，一颗金色光点是全片主角，概念变了，光点跟着变形 适合：抽象概念 · 数学 · 信息 · 宇宙。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/starfield/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/starfield/still.jpg", auto="recipe-with-skill"),
   P("vibe-darkgold", "暗场概念 · 暗金线描", "炭黑底上琥珀色发光线条一笔笔画出场景和小人，像会发光的手账 适合：职场 · 心理 · 生活里的反常 · 痛点原理。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/darkgold/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/darkgold/still.jpg", auto="recipe-with-skill"),
   P("vibe-paper", "东方 · 水墨纸本", "宣纸底、晕染远山、一笔浓墨，宋体竖排配朱砂印 适合：诗词 · 文学 · 文化 · 一条主线。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/paper/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/paper/still.jpg", auto="recipe-with-skill"),
   P("vibe-pixel", "游戏 · 像素", "16-bit 游戏关卡：像素场景、关卡名、金币和 Boss 适合：考试题型 · 方法论 · 闯关。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/pixel/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/pixel/still.jpg", auto="recipe-with-skill"),
   P("vibe-caption-news", "剪辑与纪实 · 字幕新闻", "关掉声音也能看懂：超大字幕当主角，关键词压黄块，数字滚动，来源滑入 适合：热点快讯 · 数据新闻 · 有反转的故事。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/caption-news/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/caption-news/still.jpg", auto="recipe-with-skill"),
   P("vibe-investigation", "剪辑与纪实 · 视觉调查", "把史料原文、现场图、时间线摆在一起对照：划重点、画红圈、推近定格 适合：史料考证 · 事件复盘 · 辟谣。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/investigation/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/investigation/still.jpg", auto="recipe-with-skill"),
   P("vibe-variety", "明亮流行 · 综艺花字", "亮黄旋转放射底上，粗白描边加深色厚投影的花字一个个弹出来，贴纸、对话泡、金币雨 适合：轻松科普 · 生活冷知识 · 年轻受众。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/variety/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/variety/still.jpg", auto="recipe-with-skill"),
   P("vibe-memphis", "明亮流行 · 孟菲斯波普", "奶油底上漂着锯齿、圆点、三角，积木拼出的城门，硬投影大字，高潮变沃霍尔四色格 适合：消费 · 潮流文化 · 设计史。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/memphis/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/memphis/still.jpg", auto="recipe-with-skill"),
   P("vibe-chalk", "图解与设计 · 粉笔黑板", "墨绿黑板上粉笔一笔笔画出场景，字晚半拍写出来，圈重点、列算式，板书越积越多 适合：公式 · 推导 · 物理 · 一步步讲清。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/chalk/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/chalk/still.jpg", auto="recipe-with-skill"),
   P("vibe-blueprint", "图解与设计 · 蓝图专利图", "普鲁士蓝方格纸上，先构造线、再物体线、最后尺寸线，标号、图框、红铅笔批注 适合：发明 · 古代机械 · 结构原理。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/blueprint/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/blueprint/still.jpg", auto="recipe-with-skill"),
   P("vibe-isometric", "图解与设计 · 等轴测剖面", "浅灰纸上的等轴测小城，只高亮正在讲的部件，四角读数，最后零件真的动起来 适合：机制 · 流程 · 系统怎么运转。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/isometric/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/isometric/still.jpg", auto="recipe-with-skill"),
   P("vibe-swiss", "图解与设计 · 瑞士网格动态字", "米白底 12 栏网格，超大黑字压在栏线上，红色色块推拉；字在重音砸进来，退场比进场快 适合：观点 · 数据 · 金句（字就是画面）。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/swiss/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/swiss/still.jpg", auto="recipe-with-skill"),
   P("vibe-riso", "印刷与纸 · 孔版印刷", "米色纸上荧光粉和蓝两色叠印出紫、半调网点，8 帧/秒定格，套色错位，高潮那一下对准版 适合：文化 · 艺术 · 小众冷知识。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/riso/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/riso/still.jpg", auto="recipe-with-skill"),
   P("vibe-darkmath", "暗场概念 · 深色数学", "近黑底只放正在讲的东西，木头这条线直接变成数轴，金点滑过去，×5 的弧箭头；问题先写在最上面 适合：数学 · 统计 · AI（一个对象变成下一个）。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/darkmath/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/darkmath/still.jpg", auto="recipe-with-skill"),
   P("vibe-dunhuang", "东方 · 敦煌壁画", "一层灰泥一块块剥落露出壁画，第二幅从另一侧剥出来，金箔字流光，榜题框 适合：丝路 · 佛教史 · 中外交流。档位：增强。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/dunhuang/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/dunhuang/still.jpg", auto="recipe-with-skill"),
   P("vibe-qinghua", "东方 · 青花", "白瓷底上钴蓝像墨滴进水里一样从一点晕开成画，钴蓝楷书先糊后清，青花印章 适合：器物 · 海上丝路 · 明清文化。档位：增强。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/qinghua/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/qinghua/still.jpg", auto="recipe-with-skill"),
   P("vibe-woodcut", "东方 · 木刻", "黑白版画一刀一刀刻出来，刀痕方向跟着画面斜线，红色木刻印压字，高潮硬切第二版并顿一下 适合：变法 · 起义 · 硬核历史转折。档位：增强。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/woodcut/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/woodcut/still.jpg", auto="recipe-with-skill"),
   P("vibe-collage", "印刷与纸 · 半调拼贴", "生图拆成「底 + 主体」两层，主体纸片拍下来，胶带、纸条、半调大数字、红印章，整页推走换下一页 适合：社会 · 经济 · 历史机制（Vox 式）。档位：增强。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/collage/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/collage/still.jpg", auto="recipe-with-skill"),
   P("vibe-neon", "暗场概念 · 霓虹赛博", "雨夜深紫底，霓虹灯管一节节闪着点亮，招牌字通电，「没人动」故障错位，高潮电流暴涨加扫描线 适合：科技 · 互联网 · 未来 · 赛博文化。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/neon/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/neon/still.jpg", auto="recipe-with-skill"),
   P("vibe-minimal", "东方 · 留白极简", "暖白纸上一笔墨圈，圈里一次只放一个字，底下一行小字，大片留白 适合：哲学 · 汉字 · 一个概念讲透。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/minimal/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/minimal/still.jpg", auto="recipe-with-skill"),
   P("vibe-desktop", "剪辑与纪实 · 复古桌面", "1-bit 灰点阵桌面，黑白窗口和对话框，光标就是视线，最后把「木头」图标拖进北门文件夹 适合：电脑史 · 互联网往事 · 操作过程。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/desktop/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/desktop/still.jpg", auto="recipe-with-skill"),
   P("vibe-ransom", "印刷与纸 · 剪报拼字", "灰白新闻纸上，每个字都像从不同报纸剪下来（字体、底色、角度各不相同），一个字一个字拍上去 适合：悬案 · 爆料 · 反转 · 网络梗。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/ransom/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/ransom/still.jpg", auto="recipe-with-skill"),
   P("vibe-metro", "图解与设计 · 地铁线路图", "白底上线路只走 0°/45°/90°，随剧情从南门长到北门，站点到了才亮，五十金是换乘站，列车开进终点 适合：演化路线 · 阶段 · 一条时间线。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/metro/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/metro/still.jpg", auto="recipe-with-skill"),
   P("vibe-isotype", "图解与设计 · 象形统计", "一个金锭图标 = 1 金，一个人形 = 一位围观者，一行行盖章，数量就是画面本身 适合：人口 · 数量对比 · 数据（数得出来）。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/isotype/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/isotype/still.jpg", auto="recipe-with-skill"),
   P("vibe-journal", "明亮流行 · 手账涂鸦", "点阵纸上和纸胶带、马克笔一笔笔画、荧光笔划重点、便利贴拍上去、圆珠笔吐槽 适合：学习方法 · 生活技巧 · 女性向。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/journal/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/journal/still.jpg", auto="recipe-with-skill"),
   P("vibe-titles", "电影感 · 剪影片头", "橘红底，黑色硬边色块从画外切进来拼成城门，木杆像一道竖线劈开画面，「没人动」时上下黑条合成一道缝，高潮黑块炸开 适合：悬疑 · 电影史 · 大事件开场。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/titles/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/titles/still.jpg", auto="recipe-with-skill"),
   P("vibe-silent", "电影感 · 默片字卡", "棕褐黑白胶片，颗粒、闪烁、划痕、18 帧/秒抖动；画面和花边字卡交替，光圈开合 适合：老历史 · 电影史 · 百年前的故事。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/silent/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/silent/still.jpg", auto="recipe-with-skill"),
   P("vibe-constructivist", "电影感 · 构成主义蒙太奇", "米色纸、红黑斜线构图、半调剪影人群、标语大字沿斜线撞进来、喇叭放射线 适合：运动 · 革命 · 宣言式观点。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/constructivist/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/constructivist/still.jpg", auto="recipe-with-skill"),
   P("vibe-rpg", "游戏 · RPG 对话框", "上方像素场景，下方深蓝对话框逐字打出，选项菜单里大家都停在「观望」，五十金光标跳到「搬」，弹出「获得 50 金！」 适合：两难选择 · 剧情推演 · 游戏化讲解。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/rpg/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/rpg/still.jpg", auto="recipe-with-skill"),
   P("vibe-cards", "游戏 · 卡牌对战", "绿绒桌面上卡牌翻面打出：「赏金 10」攻击「怀疑」被弹开（MISS），打出「×5」后击碎怀疑翻出「信」 适合：博弈 · 策略 · 力量对比。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/cards/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/cards/still.jpg", auto="recipe-with-skill"),
   P("vibe-keynote", "暗场概念 · 发布会极简", "纯黑底、一屏一件事、超大白字，数字在说出来的那一刻落定，五十金带渐变和光晕 适合：科技发布 · 数字冲击 · 一句话结论。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/keynote/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/keynote/still.jpg", auto="recipe-with-skill"),
   P("vibe-aurora", "暗场概念 · 极光", "深海军蓝底上紫青粉光斑缓慢流动，毛玻璃卡片一层层浮上来，数值卡在高潮时描边发光 适合：AI · 产品 · 未来趋势。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/aurora/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/aurora/still.jpg", auto="recipe-with-skill"),
   P("vibe-editorial", "印刷与纸 · 杂志编辑", "暖白纸、刊头细线、衬线大标题、两栏正文逐行排出、引语换成史记原文、斜体大数字 适合：人文 · 深度解读 · 原文引用。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/editorial/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/editorial/still.jpg", auto="recipe-with-skill"),
   P("vibe-vapor", "明亮流行 · 蒸汽波", "落日渐变天空、条纹太阳、滚动的霓虹网格地面、铬金属字；「没人动」VHS 跟踪错位；PLAY 和计时 适合：80/90 年代 · 怀旧 · 互联网文化。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/vapor/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/vapor/still.jpg", auto="recipe-with-skill"),
   P("vibe-scroll", "东方 · 长卷", "木轴从右往左展开工笔绢本长卷，题签竖排贴上，画卷继续往左卷动，放大镜推到人物局部 适合：一条时间线 · 城市生活 · 东亚史。档位：增强。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/scroll/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/scroll/still.jpg", auto="recipe-with-skill"),
   P("vibe-copper", "图解与设计 · 铜版博物", "45° 排线把灰度铜版一道道刻出来，淡彩晚一拍渗进去，左页铜版体图注逐条出现，高潮翻到标本页并编号 适合：动植物 · 博物学 · 器物与发明。档位：增强。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/copper/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/copper/still.jpg", auto="recipe-with-skill"),
   P("vibe-farm", "游戏 · 田园像素", "春天的农场村庄像素画，木框 HUD 里时钟按 10 分钟跳、金币在涨，羊皮纸对话框配像素头像，村民冒「…」，主角把东西举过头顶 适合：农业 · 生活经营 · 游戏化讲解（星露谷式）。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/farm/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/farm/still.jpg", auto="recipe-with-skill"),
   P("vibe-clay", "明亮流行 · 黏土卡哇伊", "粉色奶油底，黏土城门和豆豆村民都有小脸，出场挤压回弹，「没人动」豆豆发抖冒汗，五十金大黏土金币砸下来 适合：儿童科普 · 萌宠 · 轻松冷知识。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/clay/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/clay/still.jpg", auto="recipe-with-skill"),
   P("vibe-deco", "暗场概念 · 装饰艺术金线", "黑底，金线从中轴向两侧对称画出阶梯塔楼，顶部扇形放射线打开，数字在金框嵌板里，五十金嵌板填金 适合：奢侈品 · 金融史 · 20 年代 · 建筑。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/deco/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/deco/still.jpg", auto="recipe-with-skill"),
   P("vibe-poster", "印刷与纸 · 国家公园海报", "米色纸限定 5 色平涂，天空、远山、近山、城门、题字一版版从下往上套印，徽章写赏金，五十金太阳升起 适合：地理 · 自然 · 旅行 · 城市。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/poster/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/poster/still.jpg", auto="recipe-with-skill"),
   P("vibe-lighttable", "剪辑与纪实 · 档案灯台", "暗房里一张冷光灯台，竹简、胶片条、现场照片摊在上面，放大镜依次滑到关键字，红色油性笔圈住 适合：考古 · 文物 · 史料细读。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/lighttable/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/lighttable/still.jpg", auto="recipe-with-skill"),
   P("vibe-tvnews", "剪辑与纪实 · 电视新闻包装", "蓝色演播室底、虚构台标「VIBE 新闻 · 直播」、画中画现场、两层下方标题条、底部滚动字幕，五十金红色「突发」横幅 适合：热点 · 时事 · 事件播报（虚构台名）。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/tvnews/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/tvnews/still.jpg", auto="recipe-with-skill"),
   P("vibe-sketch", "图解与设计 · 手绘过程", "一只捏着铅笔的手一路画给你看：铅笔起稿 → 墨线描出 → 马克笔来回涂色 → 手写字，镜头跟着手走，最后拉远看全图 适合：讲原理 · 讲过程 · 一步步画给你看。档位：基础。",
     L + "/vibe-knowledge/skills/vibe-knowledge", "走 vibe-knowledge skill：选题→查证→film.js→cine 渲染；风格目录 styles/sketch/STYLE.md；增强档需 Renoise 生图。详见 skill SKILL.md 与 references/01-templates.md（六种母版）。", L + "/vibe-knowledge/skills/vibe-knowledge/styles/sketch/still.jpg", auto="recipe-with-skill"),
 ]},
]
for t in TYPES: t["presets"].append(dict(CUSTOM))
AUTO = {"script-with-spec": "可脚本重渲：新提示词需先由执行端写成 spec/episode JSON，再跑一条命令",
        "script-with-project-copy": "半自动：复制样例项目、改文案/数据后跑流水线脚本",
        "manual-remotion": "需人工：要改 Remotion/引擎工程代码或镜头，不能一键出片",
        "recipe-with-skill": "Prompt与Skill已备；尚无样片验证，不代表一键渲染"}

def thumbs(doc):
    for t in doc["types"]:
        for p in t["presets"]:
            s = p.get("thumbnail_source")
            if not s: continue
            out = ROOT / p["thumbnail"]
            if not os.path.exists(s): print("缺源", s); p["thumbnail_missing"] = True; continue
            if s.lower().endswith((".mp4", ".mov")):
                cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(p.get("thumbnail_seek") or 3), "-i", s, "-frames:v", "1", "-vf", "scale=640:-2", str(out)]
            else:
                cmd = ["ffmpeg", "-y", "-v", "error", "-i", s, "-vf", "scale=640:-2", str(out)]
            subprocess.run(cmd, stdin=subprocess.DEVNULL); p.pop("thumbnail_missing", None)
            print("ok" if out.exists() else "FAIL", p["id"])

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True); f = ROOT / "styles.json"
    if "--init" in sys.argv or not f.exists():
        doc = {"_说明": "顶层按 视频类型 分组；每个类型的 presets 末尾都有 自定义风格。thumbnail 为相对 ~/video-hub 的缓存路径，跑 build_styles.py 由 thumbnail_source 生成。automation 取值见 automation_levels。",
               "automation_levels": AUTO, "types": TYPES}
    else:
        doc = json.loads(f.read_text(encoding="utf-8"))
    thumbs(doc); f.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
