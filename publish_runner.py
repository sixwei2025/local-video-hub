"""Explicit user-click publication. Serialize shared browser access; never auto-retry."""
import fcntl, subprocess, threading
from pathlib import Path
import publish_lib as P

_ACTIVE = set()
_LOCK = threading.Lock()

def start(ids):
    def worker(jid):
        try:
            # Both adapters share the desktop, so only one real upload at a time.
            P.QUEUE.parent.mkdir(parents=True, exist_ok=True)
            with open(P.QUEUE.parent / 'publish-execution.lock', 'w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                j = P.get(jid)
                if not j or j['status'] != 'pending' or not j.get('approved_at'):
                    return
                pr = P.pause_reason()
                if pr:   # 发布暂停：不真发，任务保持 pending，不标失败
                    P.update(jid, paused_note=pr)
                    return
                try:
                    result = subprocess.run([str(P.ROOT / '.venv/bin/python'), str(P.ROOT / 'pub.py'),
                                             'run', jid, '--approved'], cwd=P.ROOT,
                                            capture_output=True, text=True, timeout=1900)
                    current = P.get(jid)
                    if result.returncode == 3 and 'PAUSED' in (result.stderr or ''):
                        pass  # 子进程发现暂停，保持 pending
                    elif current and current['status'] in ('running', 'pending'):
                        P.update(jid, status='failed', error=(result.stderr or result.stdout or '发布进程未返回结果')[-500:], finished_at=P.now())
                except Exception as e:
                    P.update(jid, status='failed', needs_verification=True,
                             error='未能确认发布结果，请先在平台核对后再决定是否重试：' + str(e)[:160], finished_at=P.now())
        finally:
            with _LOCK: _ACTIVE.discard(jid)
    for jid in ids:
        with _LOCK:
            if jid in _ACTIVE: continue
            _ACTIVE.add(jid)
        threading.Thread(target=worker, args=(jid,), daemon=True).start()
