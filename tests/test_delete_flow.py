import copy, sqlite3, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as A
import hub_lib as H

class DeletionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patches=[patch.object(A,'DB',self.root/'test.db'),patch.object(H,'DB',self.root/'test.db')]
        for p in self.patches:p.start()
        A.db().close()
        c=sqlite3.connect(A.DB);c.execute("insert into works(id,group_key,title,state,selected_path,cover_path,subtitle_path) values('work','g','样片','confirm','video','cover','sub')")
        c.execute("insert into meta(path) values('video')")
        c.execute("insert into assets(work_id,kind,path) values('work','video','video')")
        c.execute("insert into groups(key,selected_path) values('g','video')");c.commit();c.close()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        A._MEMO.clear();A._CACHE.clear();self.tmp.cleanup()
    def test_partial_delete_clears_references_keeps_other_versions(self):
        with patch.object(H.queue_lib,'load_jobs',return_value=[]):H.forget_paths(['video'],'work',False)
        c=sqlite3.connect(A.DB)
        self.assertEqual(c.execute("select selected_path from works where id='work'").fetchone(),(None,))
        self.assertEqual(c.execute("select selected_path from groups").fetchone(),(None,))
        self.assertEqual(c.execute('select count(*) from meta').fetchone()[0],0);c.close()
    def test_whole_delete_hides_completed_job_preserves_audit_record(self):
        job={'id':'job','work_id':'work','status':'done','result_paths':['video']}
        with patch.object(H.queue_lib,'load_jobs',return_value=[job]),patch.object(H.queue_lib,'patch_job') as update:
            H.forget_paths(['video'],'work',True)
            self.assertTrue(update.call_args.kwargs['deleted'])
        c=sqlite3.connect(A.DB);self.assertEqual(c.execute('select count(*) from works').fetchone()[0],0);c.close()
    def test_index_refreshes_even_if_record_cleanup_fails(self):
        f=self.root/'disposable.mp4';f.write_bytes(b'fixture')
        w={'work_title':'样片','versions_count':1};vs=[{'path':str(f)}]
        def trash(paths):f.rename(self.root/'trash.mp4');return paths,[]
        with patch.object(A,'_del_scope',return_value=(w,vs,[str(f)],False)),patch.object(H,'trash',side_effect=trash),patch.object(H,'log_delete'),patch.object(H,'forget_paths',side_effect=sqlite3.OperationalError('database is locked')),patch.object(A,'scan') as scan:
            r=A.api_delete('work',{});scan.assert_called_once();self.assertIn('locked',r['cleanup_warning']);self.assertFalse(f.exists())
    def test_missing_file_is_excluded_before_work_recreation(self):
        with patch.object(A,'_frag_ctx',return_value={}),patch.object(H,'sub_map',return_value={}):
            self.assertEqual(A._with_meta([{'path':str(self.root/'already-deleted.mp4')}]),[])

if __name__=='__main__':unittest.main()
