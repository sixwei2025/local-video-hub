#!/usr/bin/env python3
"""参考视频链接解析器：链接/分享文案 -> 本地 mp4 + 元数据(JSON)
用法: resolve_ref.py <url_or_share_text> [--out DIR] [--method auto|ytdlp|pw]
输出: {"ok":bool,"platform":..,"path":..,"title":..,"author":..,"duration":..,"cover":..,"error":..,"method":..,"need_upload":bool}
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, urllib.request, urllib.parse, urllib.error
from pathlib import Path

HOME = Path.home()
VENV = HOME / "video-hub/.venv/bin"
YTDLP = str(VENV / "yt-dlp")
DY_PROFILE = HOME / "lab/douyin-publisher/profile"
CH_CDP = "http://127.0.0.1:9333"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
MUA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
CH_MSG = "视频号链接无法直接解析，请在手机上保存视频后拖进来，或用电脑微信打开后录屏"
LOG = []
def log(*a):
    s = " ".join(map(str, a)); LOG.append(s); print(s, file=sys.stderr, flush=True)

def extract_url(text):
    text = text.strip()
    m = re.search(r"https?://[^\s\u4e00-\u9fff，。！（）()\[\]【】\"'<>]+", text)
    if m: return m.group(0).rstrip(".,;、")
    m = re.search(r"(?:v\.douyin\.com|www\.douyin\.com|douyin\.com|channels\.weixin\.qq\.com)/[\w\-/?=&.]+", text)
    return "https://" + m.group(0) if m else None

def platform_of(u):
    h = urllib.parse.urlparse(u).netloc.lower()
    if "douyin.com" in h or "iesdouyin.com" in h: return "douyin"
    if "weixin.qq.com" in h or "wechat.com" in h or "weishi" in h: return "channels"
    if h.endswith("x.com") or "twitter.com" in h or h.endswith("t.co"): return "x"
    if "bilibili.com" in h or "b23.tv" in h: return "bilibili"
    if "youtube.com" in h or "youtu.be" in h: return "youtube"
    if "xiaohongshu.com" in h or "xhslink.com" in h: return "xiaohongshu"
    return "other"

def expand(u, ua=MUA):
    req = urllib.request.Request(u, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return r.geturl()
    except urllib.error.HTTPError as e:
        return (e.headers.get("Location") or getattr(e,"url",None) or u)
    except Exception as e:
        log("expand fail", e); return u

def aweme_id(u):
    for p in (r"/video/(\d{8,})", r"/note/(\d{8,})", r"[?&](?:modal_id|aweme_id|item_id)=(\d{8,})", r"/share/(?:video|slides|note)/(\d{8,})"):
        m = re.search(p, u)
        if m: return m.group(1)
    return None

def ffprobe_dur(p):
    try:
        return round(float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",p],text=True).strip()),2)
    except Exception: return None

def hdr_download(url, dst, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r, open(dst,"wb") as o:
        shutil.copyfileobj(r, o, 1<<20)
    return os.path.getsize(dst)

def copy_profile(src):
    """只读复制 Chrome profile 到临时目录(跳过锁和缓存)，绝不写原目录"""
    tmp = Path(tempfile.mkdtemp(prefix="dyprof-"))
    skip = {"Cache","Code Cache","GPUCache","Service Worker","GrShaderCache","GraphiteDawnCache",
            "ShaderCache","DawnCache","component_crx_cache","optimization_guide_model_store",
            "Crashpad","BrowserMetrics","Default Cache"}
    def ign(d, names):
        return [n for n in names if n in skip or n.startswith("Singleton") or n.endswith(".lock") or n=="LOCK"]
    shutil.copytree(src, tmp/"p", ignore=ign, symlinks=False, ignore_dangling_symlinks=True, dirs_exist_ok=True)
    return tmp

def ytdlp(url, out, cookies_browser=None, extra=()):
    tpl = str(out / "%(extractor_key)s-%(id)s.%(ext)s")
    cmd = [YTDLP, "--no-playlist", "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
           "--merge-output-format","mp4","--write-thumbnail","--convert-thumbnails","jpg",
           "-o", tpl, "--print-json","--no-simulate","--no-progress","--socket-timeout","30", *extra]
    if cookies_browser: cmd += ["--cookies-from-browser", cookies_browser]
    cmd.append(url)
    log("yt-dlp cookies=%s" % bool(cookies_browser))
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError((p.stderr.strip().splitlines() or ["yt-dlp 失败"])[-1][:300])
    info = json.loads(p.stdout.strip().splitlines()[-1])
    path = info.get("filepath") or (info.get("requested_downloads") or [{}])[0].get("filepath") or info.get("_filename")
    if path and not os.path.exists(path) and os.path.exists(str(Path(path).with_suffix(".mp4"))):
        path = str(Path(path).with_suffix(".mp4"))
    cov = Path(path).with_suffix(".jpg") if path else None
    cover = str(cov) if cov and cov.exists() else info.get("thumbnail")
    return dict(path=path, title=info.get("title") or (info.get("description") or "")[:80],
                author=info.get("uploader") or info.get("channel") or info.get("uploader_id"),
                duration=info.get("duration") or ffprobe_dur(path), cover=cover,
                id=str(info.get("id")), method="yt-dlp")

# ---------------- 抖音 ----------------
def douyin_pw(page_url, aid, out):
    """Method B: Playwright 用 profile 临时副本，监听网络抓 aweme 详情 / video src"""
    from playwright.sync_api import sync_playwright
    prof = copy_profile(DY_PROFILE)
    hit = {"meta": None, "src": None}
    try:
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                str(prof/"p"), headless=True, user_agent=UA,
                args=["--disable-blink-features=AutomationControlled","--no-first-run","--no-default-browser-check"])
            page = ctx.new_page()
            def on_resp(r):
                u = r.url
                try:
                    if ("aweme/detail" in u or "/aweme/v1/web/aweme/detail" in u) and "json" in (r.headers.get("content-type","")):
                        hit["meta"] = r.json()
                    if (".mp4" in u or "media-video" in u or "aweme/v1/play" in u) and not hit["src"]:
                        hit["src"] = u
                except Exception: pass
            page.on("response", on_resp)
            try: page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e: log("pw goto", e)
            page.wait_for_timeout(4000)
            # 从 RENDER_DATA / video 标签兜底
            if not hit["src"]:
                try: hit["src"] = page.eval_on_selector("video","e=>e.currentSrc||e.src")
                except Exception: pass
            title=author=dur=cover=None
            m = hit["meta"]
            if m:
                d = m.get("aweme_detail") or (m.get("aweme_list") or [{}])[0]
                title = d.get("desc"); author = (d.get("author") or {}).get("nickname")
                dur = round((d.get("duration") or 0)/1000,2) or None
                try:
                    pa = d["video"]["play_addr"]["url_list"]
                    # 无水印优先
                    hit["src"] = next((x for x in pa if "playwm" not in x), pa[0])
                    cover = (d["video"].get("cover") or {}).get("url_list",[None])[0]
                except Exception: pass
            ctx.close()
            if not hit["src"]: raise RuntimeError("Playwright 未捕获到视频地址")
            dst = out / f"douyin-{aid or 'pw'}.mp4"
            hdr_download(hit["src"], str(dst), {"User-Agent": UA, "Referer": "https://www.douyin.com/"})
            return dict(path=str(dst), title=title, author=author,
                        duration=dur or ffprobe_dur(str(dst)), cover=cover, id=aid, method="playwright")
    finally:
        shutil.rmtree(prof, ignore_errors=True)

def resolve_douyin(url, out):
    full = expand(url) if "v.douyin.com" in url else url
    aid = aweme_id(full) or aweme_id(url)
    page = f"https://www.douyin.com/video/{aid}" if aid else full
    log("douyin page", page, "aid", aid)
    errs = []
    # Method A: yt-dlp with cookies
    for cb in ("chrome:%s" % DY_PROFILE, "chrome", None):
        try:
            return ytdlp(page, out, cookies_browser=cb)
        except Exception as e:
            errs.append("ytdlp(%s): %s" % (cb, e)); log("A fail", e)
    # Method B: Playwright
    try:
        return douyin_pw(page, aid, out)
    except Exception as e:
        errs.append("playwright: %s" % e); log("B fail", e)
    raise RuntimeError(" | ".join(errs[-3:]))

# ---------------- 视频号 ----------------
def resolve_channels(url, out):
    """用 9333 端口 CDP 的专用 Chrome 新开标签监听网络；视频多为加密"""
    info = {"platform":"channels","ok":False,"need_upload":True,"message":CH_MSG,"method":"cdp"}
    try:
        from playwright.sync_api import sync_playwright
        hits = {"m3u8":[], "mp4":[], "enc":False}
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(CH_CDP, timeout=8000)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
            def on_resp(r):
                u=r.url
                if ".mp4" in u: hits["mp4"].append(u)
                if ".m3u8" in u: hits["m3u8"].append(u)
                if "encrypt" in u.lower() or "/encfile" in u or "get_encrypt" in u: hits["enc"]=True
            page.on("response", on_resp)
            try: page.goto(url, wait_until="networkidle", timeout=40000)
            except Exception as e: log("ch goto", e)
            page.wait_for_timeout(5000)
            page.close()  # 不动 upload_draft 的标签
        info["captured"]={"mp4":hits["mp4"][:3],"m3u8":hits["m3u8"][:3]}
        if hits["mp4"]:
            dst = out/"channels.mp4"
            try:
                hdr_download(hits["mp4"][0], str(dst), {"User-Agent":UA,"Referer":"https://channels.weixin.qq.com/"})
                if os.path.getsize(dst)>10000:
                    return dict(ok=True, platform="channels", path=str(dst), title=None, author=None,
                                duration=ffprobe_dur(str(dst)), cover=None, method="cdp", error=None)
            except Exception as e: log("ch dl", e)
        info["error"]="视频号视频通常为加密流(encrypted)，无法直接解码。"+CH_MSG
    except Exception as e:
        info["error"]="无法连接视频号专用 Chrome(9333) 或页面加载失败: %s。%s"%(e,CH_MSG)
    info["title"]=info["author"]=info["path"]=info["duration"]=info["cover"]=None
    return info

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=str(HOME/"video-hub/uploads/refs/"))
    ap.add_argument("--method", default="auto")
    a = ap.parse_args()
    out = Path(os.path.expanduser(a.out)); out.mkdir(parents=True, exist_ok=True)
    url = extract_url(a.input)
    res = {"ok":False,"platform":None,"path":None,"title":None,"author":None,"duration":None,"cover":None,"error":None,"method":None}
    if not url:
        res["error"]="未在输入中找到链接"; print(json.dumps(res,ensure_ascii=False)); return 1
    plat = platform_of(url); res["platform"]=plat
    log("input url", url, "platform", plat)
    try:
        if plat=="douyin":
            r = resolve_douyin(url, out)
        elif plat=="channels":
            r = resolve_channels(url, out)
            res.update({k:r.get(k) for k in res}); res["platform"]="channels"
            res["need_upload"]=r.get("need_upload",True); res["message"]=r.get("message",CH_MSG)
            if not r.get("ok"): print(json.dumps(res,ensure_ascii=False)); return 2
            res["ok"]=True; print(json.dumps(res,ensure_ascii=False)); return 0
        elif plat in ("x","bilibili","youtube","xiaohongshu","other"):
            cb = "chrome" if plat in ("x","bilibili","xiaohongshu") else None
            try: r = ytdlp(url, out, cookies_browser=cb)
            except Exception:
                r = ytdlp(url, out, cookies_browser=None)
        else:
            raise RuntimeError("不支持的平台")
        if not r.get("path") or not os.path.exists(r["path"]):
            raise RuntimeError("下载后未找到文件")
        res.update(ok=True, path=r["path"], title=r.get("title"), author=r.get("author"),
                   duration=r.get("duration"), cover=r.get("cover"), method=r.get("method"))
        print(json.dumps(res,ensure_ascii=False)); return 0
    except Exception as e:
        res["error"]=str(e)[:500]; res["log"]=LOG[-6:]
        print(json.dumps(res,ensure_ascii=False)); return 1

if __name__=="__main__":
    sys.exit(main())
