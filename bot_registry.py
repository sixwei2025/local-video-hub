"""Human-confirmed production roster; publisher is intentionally excluded."""
import json,re
from pathlib import Path
REGISTRY=Path(__file__).with_suffix('.json')
def load():return json.loads(REGISTRY.read_text(encoding='utf-8'))
def key(s):return re.sub(r'[\s·：:._-]+','',str(s or '')).lower()
def canonical(name):
 name=(name or '').strip()
 data=load()
 if any(key(name)==key(x) for x in data.get('excluded_roles',[])):raise ValueError('短视频发布官只负责发布，不加入制作与修改分发')
 hit=next((b['name'] for b in data['bots'] if key(b['name'])==key(name)),None)
 if hit: return hit
 for old,new in (data.get('aliases') or {}).items():
  if key(name)==key(old):
   return next((b['name'] for b in data['bots'] if key(b['name'])==key(new)), new)
 return name
def responsible(video_type='',line=''):
 bots=load()['bots']
 return next((b['name'] for b in bots if video_type and video_type in b['types']),None) or next((b['name'] for b in bots if line and line in b['lines']),None) or ''
