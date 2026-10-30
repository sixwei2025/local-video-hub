import sys,tempfile,sqlite3
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import queue_lib as Q,hub_lib as H,hub
class ProducerTest(TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name)
  self.ps=[patch.object(Q,'QUEUE',p/'jobs.jsonl'),patch.object(Q,'LOCK',p/'jobs.lock'),patch.object(H,'DB',p/'meta.db')]
  for x in self.ps:x.start()
  H.db().close()
 def tearDown(self):
  for x in reversed(self.ps):x.stop()
  self.tmp.cleanup()
 def test_proactive_new_preserves_producer_after_stage_change(self):
  wid,*_=hub.new_work('真实机器人A','promo','测试作品');H.stage(wid,'渲染中')
  c=H.db();self.assertEqual(H.work_view(c,wid)['producer_bot'],'真实机器人A');c.close()
 def test_directed_revision_and_current_version(self):
  wid,*_=hub.new_work('机器人A','promo','测试作品')
  j=H.revise(wid,'修改封面','version2','/test/version2.mp4')
  self.assertEqual(j['target_bot'],'机器人A');self.assertEqual(j['source_video'],'/test/version2.mp4')
  self.assertIsNone(H.next_job('机器人B'));self.assertEqual(H.next_job('机器人A')['id'],j['id'])
  self.assertFalse(Q.claim_job(j['id'],'机器人B'));self.assertTrue(Q.claim_job(j['id'],'机器人A'));self.assertFalse(Q.claim_job(j['id'],'机器人A'))
 def test_unknown_owner_is_not_claimed_then_binding_routes_saved_opinion(self):
  wid,*_=hub.new_work('登记前','promo','测试作品');c=H.db();c.execute("update works set producer_bot=null,video_type=null,line=null where id=?",(wid,));c.commit();c.close()
  j=H.revise(wid,'修改封面');self.assertEqual(j['dispatch_state'],'unassigned');self.assertFalse(Q.claim_job(j['id']))
  H.set_producer(wid,'机器人B');j=H._job(j['id']);self.assertEqual(j['target_bot'],'机器人B');self.assertTrue(Q.claim_job(j['id'],'机器人B'))

 def test_role_routing_does_not_invent_historical_creator(self):
  wid,*_=hub.new_work('旧机器人','promo','测试作品');c=H.db();c.execute('update works set producer_bot=null where id=?',(wid,));c.commit();c.close()
  j=H.revise(wid,'修改封面');self.assertEqual(j['target_bot'],'短视频操盘手 6·宣传片');self.assertEqual(j['routing_basis'],'responsibility')
  c=H.db();self.assertIsNone(H.work_view(c,wid)['producer_bot']);c.close()
 def test_publisher_is_excluded_and_leader_only_handles_misc(self):
  import bot_registry as R
  self.assertEqual(R.responsible('hotnews','lab'),'短视频部门负责人·实验室')
  self.assertEqual(R.responsible('psych','lab'),'短视频操盘手1·心理科普')
  with self.assertRaises(ValueError):R.canonical('短视频发布官')
