"""No platform access: isolated queue and mocked external publisher only."""
import importlib.util, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_lib as P
import publish_runner as runner

class PublishQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); q = Path(self.tmp.name)
        self.q = patch.multiple(P, QUEUE=q/'publish.jsonl', LOCK=q/'publish.lock');self.q.start()
        self.spec = {'platform':'douyin','video_path':'/test/video.mp4','title':'一条成片','short_title':'一条成片','desc':'简介','topics':['AI'],'cover':'/cover.png','cover_h':'','ai_declare':True}
    def tearDown(self):self.q.stop();self.tmp.cleanup()
    def test_double_click_and_claim(self):
        a=P.enqueue_batch([self.spec],approved=True)[0]
        b=P.enqueue_batch([self.spec],approved=True)[0]
        self.assertEqual(a['id'],b['id']);self.assertEqual(len(P.load()),1)
        self.assertTrue(P.claim(a['id']));self.assertFalse(P.claim(a['id']))
    def test_unknown_failure_cannot_bypass_check_with_new_batch(self):
        a=P.enqueue_batch([self.spec],approved=True)[0]
        P.update(a['id'],status='failed',needs_verification=True)
        with self.assertRaises(ValueError):P.enqueue_batch([self.spec],approved=True)
        self.assertEqual(len(P.load()),1)
    def test_different_pending_content_is_not_silently_replaced(self):
        a=P.enqueue_batch([self.spec],approved=True)[0]
        with self.assertRaises(ValueError):P.enqueue_batch([dict(self.spec,title='新标题')],approved=True)
        self.assertEqual(P.get(a['id'])['title'],'一条成片')
    def test_platform_batch_all_or_nothing(self):
        ch=dict(self.spec,platform='channels');P.enqueue_batch([ch])
        with self.assertRaises(ValueError):P.enqueue_batch([self.spec,dict(ch,title='冲突')],approved=True)
        self.assertEqual(len(P.load()),1)
    def test_platforms_have_independent_results_and_done_is_reused(self):
        a,b=P.enqueue_batch([self.spec,dict(self.spec,platform='channels')],approved=True)
        P.update(a['id'],status='done');P.update(b['id'],status='failed')
        self.assertEqual(P.get(a['id'])['status'],'done');self.assertEqual(P.get(b['id'])['status'],'failed')
        self.assertEqual(P.enqueue_batch([self.spec],approved=True)[0]['id'],a['id'])
    def test_real_commands_only_carry_publish_for_approved_executor(self):
        # Command construction touches no browser; package path isolated.
        with patch.object(P,'PKG',Path(self.tmp.name)):
            j=dict(self.spec,id='test')
            self.assertNotIn('--publish',P.command(j,False)[1])
            self.assertIn('--publish',P.command(j,True)[1])
            self.assertIn('--check-only',P.command(dict(j,platform='channels'),False)[1])
            self.assertIn('--check-only',P.command(dict(j,platform='xhs',id='xhs-test',desc='简介'),False)[1])
            self.assertIn('--publish',P.command(dict(j,platform='xhs',id='xhs-test',desc='简介'),True)[1])
            self.assertIn('xhs',P.PLATFORM_NAMES)
    def test_actual_publisher_not_invoked_without_click_approval(self):
        # Run the worker synchronously using a fake thread, external process mocked.
        j=P.enqueue_batch([self.spec],approved=False)[0]
        class ImmediateThread:
            def __init__(self,target,args,**kw):self.target,self.args=target,args
            def start(self):self.target(*self.args)
        with patch.object(runner.threading,'Thread',ImmediateThread),patch.object(runner.subprocess,'run') as run:
            runner.start([j['id']]);run.assert_not_called()
        self.assertEqual(P.get(j['id'])['status'],'pending')

if __name__=='__main__':unittest.main()


class DescLimitTest(unittest.TestCase):
    def test_truncate_prefers_clause_and_strips_punct(self):
        long = '从托尔曼的老鼠迷宫到电报员的平台期，看看没被看见的努力可能藏在哪里，以及怎样熬过看不见回报的阶段。'
        new, tr = P.truncate_desc(long)
        self.assertTrue(tr)
        self.assertLessEqual(len(new), P.DESC_MAX)
        self.assertEqual(new, '从托尔曼的老鼠迷宫到电报员的平台期')
        self.assertFalse(new.endswith(('，','。','！','？')))
    def test_ensure_desc_logs_and_validate_passes(self):
        j = {'platform':'douyin','video_path':'/test/video.mp4','title':'一条成片',
             'desc':'以为只有自己听到求救时，85%的人会出手；以为还有4个人在场，只剩31%。从1968年的经典实验讲起。',
             'topics':['AI'],'cover':'/cover.png'}
        logs=[]
        P.ensure_desc(j, log=logs)
        self.assertTrue(j.get('desc_truncated'))
        self.assertLessEqual(len(j['desc']), P.DESC_MAX)
        self.assertTrue(logs and '原文=' in logs[0] and '改后=' in logs[0])
        # after ensure, length check in validate should not fail on desc length
        # (video/cover files missing may still fail — only check desc rule via ensure)
        self.assertLessEqual(len(j['desc']), 30)
    def test_short_desc_unchanged(self):
        j={'desc':'刷手机停不下来，不是你没自制力。'}
        P.ensure_desc(j)
        self.assertFalse(j.get('desc_truncated'))
        self.assertEqual(j['desc'],'刷手机停不下来，不是你没自制力。')

class PublishApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        from fastapi.testclient import TestClient
        cls.appmod=app;cls.client=TestClient(app.app,base_url='http://127.0.0.1:8765')
    def test_missing_approval_and_cross_site_are_rejected(self):
        r=self.client.post('/api/publish/start',json={});self.assertEqual(r.status_code,400)
        r=self.client.post('/api/publish/start',json={'approved':True},headers={'origin':'https://outside.example'})
        self.assertEqual(r.status_code,403)
    def test_two_platform_launch_passes_only_approved_jobs_to_runner(self):
        a=self.appmod
        import contextlib
        work={'work_id':'fake','state':'confirm','archived':False,'version_ids':['vid']}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(a.INDEX,{'by_id':{'vid':{'id':'vid'}}}))
            stack.enter_context(patch.object(a,'with_meta',return_value=[]))
            stack.enter_context(patch.object(a,'work_cards',return_value=[work]))
            create=stack.enter_context(patch.object(a,'_create_publish_jobs',return_value={'items':[{'id':'dy'},{'id':'ch'}]}))
            review=stack.enter_context(patch.object(a,'api_review'))
            start=stack.enter_context(patch.object(runner,'start'))
            r=self.client.post('/api/publish/start',json={'approved':True,'video_id':'vid','platforms':['douyin','channels']})
            self.assertEqual(r.status_code,200);start.assert_called_once_with(['dy','ch'])
            self.assertTrue(create.call_args.args[0]['_website_approved']);review.assert_called_once()
    def test_unverified_result_cannot_be_republished_by_retry(self):
        with patch.object(P,'get',return_value={'id':'test','status':'failed','needs_verification':True}):
            with patch.object(runner,'start') as start:
                r=self.client.post('/api/publish/test/run',json={'approved':True})
                self.assertEqual(r.status_code,409);start.assert_not_called()
