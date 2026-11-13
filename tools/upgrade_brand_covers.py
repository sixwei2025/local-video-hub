#!/opt/homebrew/bin/python3.11
# -*- coding: utf-8 -*-
"""汇芯品牌视频中心 (~/video-hub) 封面批量升级与缓存刷新工具

将本地视频中心里老旧的「黑底弹窗传单封面」「白底方框工牌照封面」「粗糙锯齿抠图红底封面」「16:9 强裁截断封面」
统一升级为「汇芯品牌视频封面 6 大标准家族」，并自动更新 SQLite `meta.db` 的 `cover_path` 与清理缩略图缓存 `cache/thumbs/wc_*.jpg`。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HUB_DIR = Path("/Users/yuanliuwei/video-hub")
TOOLS_DIR = HUB_DIR / "tools"
COVERS_OUT_DIR = HUB_DIR / "uploads" / "brand_covers"
THUMBS_DIR = HUB_DIR / "cache" / "thumbs"
DB_PATH = HUB_DIR / "data" / "meta.db"

sys.path.insert(0, str(TOOLS_DIR))
from render_video_cover import render_cover_pair, build_contact_sheet

UPGRADE_JOBS = [
    # 1. 公众号九步硬闸流水线宣传片
    dict(
        work_id="a074b933b9b4",
        slug="a074b933b9b4_wechat_autopilot",
        preset="huixin-tech-flagship",
        kicker="WECHAT AUTOPILOT · 旗舰开源",
        brand="9-STEP PIPELINE",
        metric="9步闭环",
        metric_label="HOTSPOT RADAR · MECHANICAL GATE · AUTO DRAFT",
        title_lines=["把规矩写进代码", "一人就是编辑部"],
        subtitle="一句话跑完公众号九步硬闸流水线 · 零废话直达草稿箱",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="GITHUB · SIXWEI2025",
    ),
    # 2. 汇芯 Skill 管家宣传片（使用真实软件界面画框）
    dict(
        work_id="6c2d71f2114b",
        slug="6c2d71f2114b_skills_manager",
        preset="huixin-ui-showcase",
        kicker="HUIXIN SKILLS MANAGER · 中央大脑",
        brand="Skills Hub",
        title_lines=["统管全机技能", "AI技能中央大脑"],
        subtitle="536 项技能去重精选 · 4 大 Agent 工具一键同步",
        shot="/Users/yuanliuwei/Workbuddy/github-skills-14/huixin-skills-manager/assets/showcase/01-real-interface.png",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="REAL INTERFACE",
    ),
    # 3. 袁六伟介绍视频：我走过的弯路，和交付的结果（创始人黑金杂志风）
    dict(
        work_id="73bc519159fc",
        slug="73bc519159fc_founder_results",
        preset="huixin-founder-gold",
        kicker="袁六伟 · 创业实战与交付复盘",
        brand="HUIXIN AI",
        title_lines=["我走过的弯路", "和交付的结果"],
        subtitle="学员 7000+ · 服务商单客户 100+ · 覆盖近 20 个行业",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="FOUNDER EDITION",
    ),
    # 4. 袁六伟介绍视频：从时薪20块到一人AI公司（汇芯经典红白杂志风）
    dict(
        work_id="019be8443508",
        slug="019be8443508_founder_story",
        preset="huixin-brand-red",
        kicker="个人IP定位 · 真实创业故事",
        brand="台州汇芯",
        title_lines=["从时薪20块", "到一人AI公司"],
        subtitle="把复杂技术讲人话 · 做拿走就能跑的 AI 智能体",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="HUIXIN BRAND RED",
    ),
    # 5. 视频中心宣传片 video-shotcraft（修复「6000+学员」过时基线 + 锯齿抠图）
    dict(
        work_id="c3a3e866e922",
        slug="c3a3e866e922_video_shotcraft",
        preset="huixin-founder-gold",
        kicker="LOCAL VIDEO HUB · 汇芯视频中心",
        brand="AI STUDIO",
        title_lines=["一个人", "就是一家视频公司"],
        subtitle="学员 7000+ · 服务商单客户 100+ · 多 AI 员工协同交片",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="VIDEO HUB",
    ),
    # 6. 视频网站宣传片 huashu-motion（修复「人，就是一家视步」16:9 横帧被拦腰截断的严重事故）
    dict(
        work_id="bad61100c751",
        slug="bad61100c751_video_hub_web",
        preset="huixin-tech-flagship",
        kicker="HUIXIN VIDEO HUB · 本地审片云台",
        brand="4-STAGE WORKFLOW",
        metric="70%去重",
        metric_label="MAKING · CONFIRM · READY · PUBLISHED",
        title_lines=["多AI员工交片", "本地审片总控台"],
        subtitle="选题 70% 相似度去重门闸 · 四态流转一键定稿",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="LOCAL WEB HUB",
    ),
    # 7. 汇芯品牌宣传片（修复锯齿抠图与旧数据）
    dict(
        work_id="902dfbc5ab38",
        slug="902dfbc5ab38_huixin_brand",
        preset="huixin-brand-red",
        kicker="台州汇芯 · 一人AI公司作战中枢",
        brand="HUIXIN STUDIO",
        title_lines=["一个人", "就是一家视频公司"],
        subtitle="学员 7000+ · 服务商单客户 100+ · 覆盖近 20 个行业",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="BRAND PROMO",
    ),
    # 8. 口播热点：微软让6万人自愿离职（修复锯齿抠图红底封面）
    dict(
        work_id="ae54f4b20485",
        slug="ae54f4b20485_microsoft_60k",
        preset="huixin-founder-gold",
        kicker="AI 行业风暴 · 深度热点洞察",
        brand="BIG TECH",
        title_lines=["微软6万人", "背后的AI换血"],
        subtitle="巨头裁员买算力 · 普通人如何守住不可替代性",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="HOTNEWS INSIGHT",
    ),
    # 9. WorkBuddy 教程：做视频必须装的6个skill（替换廉价 3D 发光球封面）
    dict(
        work_id="5c7b0d127991",
        slug="5c7b0d127991_six_video_skills",
        preset="huixin-klein-data",
        kicker="AI VIDEO SUITE · 生产力工具栈",
        brand="WorkBuddy",
        metric="6大Skill",
        metric_label="CUT-AS-CODE · FFMPEG · REMOTION · VOICEBOX",
        title_lines=["做视频必装Skill", "10分钟出大片"],
        subtitle="从脚本、克隆配音、运镜到双画幅封面全自动闭环",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="SWISS KLEIN",
    ),
    # 10. WorkBuddy 教程：Skill上架变现（替换波浪剪贴画封面）
    dict(
        work_id="9819f84afeb4",
        slug="9819f84afeb4_skill_monetize",
        preset="huixin-editorial-paper",
        kicker="WORKBUDDY 实操 · 技能资产化",
        brand="Skill 变现",
        title_lines=["写好一个Skill", "上架持续变现"],
        subtitle="把十年行业经验封装成可复用的 AI 技能资产",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="EDITORIAL PAPER",
    ),
    # 11. WorkBuddy 教程：一句话做出网站（替换纯红底无排版大字封面）
    dict(
        work_id="3c0f675728d7",
        slug="3c0f675728d7_one_sentence_web",
        preset="huixin-tech-flagship",
        kicker="WORKBUDDY 实操 · 零代码开发",
        brand="WEB BUILDER",
        metric="1句话",
        metric_label="PROMPT TO PRODUCTION · FULL-STACK DEPLOY",
        title_lines=["零代码写网站", "3分钟直接上线"],
        subtitle="不用懂前端框架 · 一句话生成高颜值响应式官网",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="WORKBUDDY LAB",
    ),
    # 12. WorkBuddy 教程：一句话做小程序
    dict(
        work_id="9656ef6c02ed",
        slug="9656ef6c02ed_one_sentence_miniapp",
        preset="huixin-klein-data",
        kicker="WORKBUDDY 实操 · 微信生态落地",
        brand="MINI PROGRAM",
        metric="0代码",
        metric_label="WECHAT MINI-APP · AUTO GENERATION",
        title_lines=["一句话做小程序", "打通私域变现"],
        subtitle="从页面交互到本地调试 · 保姆级全流程实操",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="SWISS KLEIN",
    ),
]


def main():
    COVERS_OUT_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    generated_covers = []
    for job in UPGRADE_JOBS:
        wid = job["work_id"]
        slug = job["slug"]
        job_dir = COVERS_OUT_DIR / slug
        res = render_cover_pair(
            job,
            job_dir,
            preset_key=job.get("preset"),
            out_3x4_name=f"{slug}_3x4.png",
            out_16x9_name=f"{slug}_16x9.png",
            dpr=2,
        )
        new_cover_jpg = Path(res["cover_3x4_jpg"])
        generated_covers.append(new_cover_jpg)

        # 读取旧 cover_path，若可直接覆盖则同步写回原路径，同时将 meta.db 指向稳定可访问的 uploads/brand_covers/
        cur.execute("SELECT title, cover_path FROM works WHERE id = ?", (wid,))
        row = cur.fetchone()
        old_cover = row[1] if row else ""
        if old_cover:
            try:
                if os.path.isfile(old_cover):
                    shutil.copy2(new_cover_jpg, old_cover)
            except Exception:
                pass

        cur.execute(
            "UPDATE works SET cover_path = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (str(new_cover_jpg), wid),
        )

        # 删除旧缩略图缓存并立刻生成最新高清缩略图 wc_{wid}.jpg
        thumb_file = THUMBS_DIR / f"wc_{wid}.jpg"
        try:
            if thumb_file.exists():
                thumb_file.unlink()
            im = Image.open(new_cover_jpg).convert("RGB")
            tw = 480
            th = round(tw * im.height / im.width)
            im.resize((tw, th), Image.LANCZOS).save(thumb_file, quality=92)
        except Exception as e:
            print(f"   ⚠ 缩略图刷新警告 ({wid}): {e}")

        status = "✅" if res["ok"] else "❌"
        print(f"{status} [{wid}] {job['title_lines'][0]}|{job['title_lines'][1]} -> {new_cover_jpg}")

    conn.commit()
    conn.close()

    sheet_out = COVERS_OUT_DIR / "upgraded_hub_covers_grid.jpg"
    build_contact_sheet(generated_covers, sheet_out, cols=4)
    print(f"\n🎉 已完成 12 个核心品牌/实操视频封面升级并写入 meta.db！总览图: {sheet_out}")


if __name__ == "__main__":
    main()
