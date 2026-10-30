#!/usr/bin/env python3
"""热点新闻横屏封面 1920x1080，与口播封面同款（~/GrokBridge/口播/_cover_template/make_cover.py）：
品牌红 #C8102E 径向渐变 + 颗粒纸感 + 柔光；顶部「袁六伟 · 一人AI公司」细线小字；奶白眉标；
两行思源黑体 Black 大字（白 + 奶白，深红投影）；细线 + 副标题；右侧六伟真人抠图半身（轮廓光、底部淡出）。
标题/眉标/副标题全部落在中央 810px 安全区（x 555–1365），3:4 居中裁切也完整。
用法：
  ~/GrokBridge/口播/_cover_template/.venv/bin/python ~/video-hub/tools/hotnews_cover.py \
     --line1 "4万个账号" [--line2 "AI额度被多扣"] [--kicker "一个周末"] [--subtitle "..."] \
     [--bg 背景图.jpg] [--no-person] --out cover.png [--sheet sheet.jpg]
  （hotnews_cover.sh 是同参数的包装）
"""
import argparse, os, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
T=os.path.expanduser('~/GrokBridge/口播/_cover_template')
W,H=1920,1080; SAFE=810; SX0=(W-SAFE)//2
RED=(200,16,46); DEEP=(92,6,20); CREAM=(248,236,220)
TITLE=os.path.join(T,'fonts','NotoSansCJKsc-Black.otf'); AUX=os.path.join(T,'fonts','NotoSansCJK-Bold.ttc')
BANNED=['采集快照','快照','抓取','AI生成','AI 生成','ai生成']

def bg(path):
    y,x=np.mgrid[0:H,0:W].astype(np.float32)
    r=np.sqrt(((x-W/2)/W*1.2)**2+((y-H*0.42)/H)**2)
    t=np.clip(r*1.45,0,1)[...,None]**1.3
    base=np.array(RED,np.float32)*(1-t)+np.array(DEEP,np.float32)*t
    if path:  # 可选背景图：灰度后按红色调叠入（multiply 30%），不抢标题
        g=ImageOps.fit(Image.open(path).convert('L'),(W,H)).filter(ImageFilter.GaussianBlur(3))
        g=np.array(g,np.float32)[...,None]/255
        base=base*(0.70+0.30*g)
    base*=1+0.10*np.clip(1-r*2.2,0,1)[...,None]
    rng=np.random.default_rng(7); n=rng.normal(0,1,(H,W)).astype(np.float32)
    n=np.array(Image.fromarray(((n*40)+128).clip(0,255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)),np.float32)-128
    base+=n[...,None]*0.18
    return Image.fromarray(base.clip(0,255).astype(np.uint8))

def person(photo,h):
    cut=os.path.splitext(photo)[0]+'_cut.png'
    if not os.path.exists(cut):
        from rembg import remove,new_session
        remove(Image.open(photo).convert('RGB'),session=new_session('isnet-general-use'),alpha_matting=True).save(cut)
    p=Image.open(cut).convert('RGBA'); p=p.crop(p.getbbox()); s=h/p.height
    p=p.resize((int(p.width*s),h),Image.LANCZOS); rgb=p.convert('RGB'); a=p.getchannel('A')
    rgb=ImageEnhance.Contrast(rgb.filter(ImageFilter.UnsharpMask(2,90,2))).enhance(1.08)
    arr=np.array(rgb,np.float32); arr[...,0]*=1.03; arr[...,2]*=0.97
    aa=np.array(a.filter(ImageFilter.GaussianBlur(0.8)),np.float32); k=int(aa.shape[0]*0.22); aa[-k:]*=np.linspace(1,0,k)[:,None]**1.4
    o=Image.fromarray(arr.clip(0,255).astype(np.uint8)).convert('RGBA'); o.putalpha(Image.fromarray(aa.astype(np.uint8))); return o

def fit(d,t,maxw,size):
    while size>40:
        f=ImageFont.truetype(TITLE,size)
        if d.textlength(t,font=f)<=maxw: return f
        size-=4
    return ImageFont.truetype(TITLE,size)

def tw(d,t,f,sp): return d.textlength(t,font=f)+sp*(len(t)-1)
def ctext(d,y,t,f,fill,sp=0):
    x=(W-tw(d,t,f,sp))/2
    for ch in t: d.text((x,y),ch,font=f,fill=fill); x+=d.textlength(ch,font=f)+sp

def make(a):
    for s in (a.line1,a.line2,a.kicker,a.subtitle,a.brand):
        for b in BANNED:
            if b.lower() in (s or '').lower(): raise SystemExit(f'封面文字含禁用词「{b}」：{s}')
    im=bg(a.bg).convert('RGBA')
    if not a.no_person:
        ph=person(a.photo,a.person_h); room=W-(SX0+SAFE)-30   # 人像只放在安全区右侧，不压标题
        if ph.width>room: ph=person(a.photo,int(a.person_h*room/ph.width))
        px=W-ph.width-15; py=H-ph.height+30
        m=Image.new('L',im.size,0); m.paste(ph.getchannel('A').filter(ImageFilter.MaxFilter(9)),(px,py))
        rim=Image.new('RGBA',im.size,(0,0,0,0)); rim.paste(Image.new('RGBA',im.size,(255,214,190,255)),mask=m.filter(ImageFilter.GaussianBlur(22)).point(lambda v:int(v*0.55)))
        im=Image.alpha_composite(im,rim); im.alpha_composite(ph,(px,py))
    d=ImageDraw.Draw(im)
    fa=ImageFont.truetype(AUX,30,index=2); ctext(d,58,a.brand,fa,CREAM+(230,),8)
    w=tw(d,a.brand,fa,8)
    for sx in (W/2-w/2-100,W/2+w/2+20): d.line((sx,79,sx+80,79),fill=CREAM+(160,),width=2)
    lines=[l for l in (a.line1,a.line2) if l]
    fs=[fit(d,lines[0],760,190)]+([fit(d,lines[1],770,180)] if len(lines)>1 else [])
    if len(lines)>1: m_=min(f.size for f in fs); fs=[ImageFont.truetype(TITLE,min(f.size,int(m_*1.12))) for f in fs]
    th=sum(int(f.size*1.12) for f in fs)
    blk=(100 if a.kicker else 0)+th+(100 if a.subtitle else 0)
    y=max(150,(H-blk)//2-10)
    if a.kicker:
        fk=ImageFont.truetype(AUX,36,index=2); kw=tw(d,a.kicker,fk,6)
        d.rectangle((W/2-kw/2-26,y,W/2+kw/2+26,y+60),fill=CREAM); ctext(d,y+7,a.kicker,fk,RED,6); y+=96
    sh=Image.new('RGBA',im.size,(0,0,0,0)); sd=ImageDraw.Draw(sh); ys=[]
    for t,f in zip(lines,fs): ys.append(y-16); ctext(sd,y-6,t,f,(40,0,8,160)); y+=int(f.size*1.12)
    im=Image.alpha_composite(im,sh.filter(ImageFilter.GaussianBlur(14))); d=ImageDraw.Draw(im)
    cols=[(255,255,255),CREAM]
    for i,(t,f) in enumerate(zip(lines,fs)): ctext(d,ys[i],t,f,cols[i] if len(lines)>1 else (255,255,255))
    if a.subtitle:
        f2=ImageFont.truetype(AUX,38,index=2); sw=min(tw(d,a.subtitle,f2,4),780); y+=14
        d.line((W/2-sw/2,y,W/2+sw/2,y),fill=CREAM+(140,),width=2); ctext(d,y+20,a.subtitle,f2,CREAM,4)
    yy=np.linspace(0,1,200)[:,None]**1.6; fade=np.zeros((200,W,4),np.uint8); fade[...,:3]=DEEP; fade[...,3]=(yy*200).astype(np.uint8)
    im.alpha_composite(Image.fromarray(fade),(0,H-200))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)),exist_ok=True)
    out=im if a.out.lower().endswith('.png') else im.convert('RGB')
    out.save(a.out,**({} if a.out.lower().endswith('.png') else {'quality':93})); return im.convert('RGB')

def sheet(im,out):
    c34=im.crop((SX0,0,SX0+SAFE,H)).resize((540,720)); full=im.resize((1280,720))
    s=Image.new('RGB',(1280+540+60,800),(30,30,30)); d=ImageDraw.Draw(s); f=ImageFont.truetype(AUX,26,index=2)
    s.paste(full,(20,60)); s.paste(c34,(1320,60)); d.text((20,18),'16:9 原图',font=f,fill=(230,)*3); d.text((1320,18),'3:4 居中裁切(810)',font=f,fill=(230,)*3)
    s.save(out,quality=90)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--line1',required=True); ap.add_argument('--line2',default='')
    ap.add_argument('--kicker',default=''); ap.add_argument('--subtitle',default='')
    ap.add_argument('--brand',default='袁六伟 · 一人AI公司'); ap.add_argument('--bg',default='')
    ap.add_argument('--photo',default=os.path.join(T,'liuwei_real.jpg')); ap.add_argument('--person_h',type=int,default=760)
    ap.add_argument('--no-person',dest='no_person',action='store_true')
    ap.add_argument('--out',required=True); ap.add_argument('--sheet',default='')
    a=ap.parse_args(); im=make(a)
    if a.sheet: sheet(im,a.sheet)
    print('saved',a.out)
