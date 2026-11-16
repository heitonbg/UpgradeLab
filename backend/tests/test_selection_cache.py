import unittest
from types import SimpleNamespace
from app.services.selection_cache import selection_scope,memoized_check
from app.services.builds import desktop_gpu

class SelectionCacheTests(unittest.TestCase):
    def test_scope_does_not_keep_old_results_or_share_mutable_results(self):
        calls=[]
        @memoized_check
        def check(row):
            calls.append(row.name)
            return {"name":row.name}
        @selection_scope
        def select(row):
            first=check(row);first["name"]="changed locally"
            return check(row)
        row=SimpleNamespace(name="before")
        self.assertEqual(select(row),{"name":"before"})
        row.name="after"
        self.assertEqual(select(row),{"name":"after"})
        self.assertEqual(calls,["before","after"])
    def test_professional_gpus_are_not_gaming_candidates(self):
        self.assertFalse(desktop_gpu("Radeon Pro W5700"))
        self.assertFalse(desktop_gpu("NVIDIA RTX A4000"))
        self.assertTrue(desktop_gpu("Radeon RX 5700 XT"))
        self.assertTrue(desktop_gpu("GeForce RTX 4070"))
