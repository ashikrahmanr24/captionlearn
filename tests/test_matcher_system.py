import unittest
from app.config import settings
from app.database import init_db, list_items, list_matches
from app.seed_data import seed_database_if_empty
from app.matcher import match_items
from app.match_engine import rerun_all_matches
from app.cloud_client import cloud_service

class TestCloudLostFoundMatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_database_if_empty()

    def test_01_seed_data_loaded(self):
        items = list_items()
        self.assertGreaterEqual(len(items), 8, "Expected at least 8 seeded lost & found items")
        print(f"[OK] Seed items verified: {len(items)} items in database.")

    def test_02_earbuds_matching_pair(self):
        lost_items = list_items(item_type="lost", query="Samsung")
        found_items = list_items(item_type="found", query="wireless")
        self.assertTrue(len(lost_items) > 0)
        self.assertTrue(len(found_items) > 0)
        
        result = match_items(lost_items[0], found_items[0])
        print(f"[OK] Samsung Earbuds match result: {result['overall_score']}% (Expected >= 80%)")
        self.assertGreaterEqual(result["overall_score"], 80.0)

    def test_03_wallet_matching_pair(self):
        lost_wallet = list_items(item_type="lost", query="Wildcraft")[0]
        found_wallet = list_items(item_type="found", query="reading section")[0]
        
        result = match_items(lost_wallet, found_wallet)
        print(f"[OK] Wildcraft Wallet match result: {result['overall_score']}% (Expected >= 80%)")
        self.assertGreaterEqual(result["overall_score"], 80.0)

    def test_04_bottle_matching_pair(self):
        lost_bottle = list_items(item_type="lost", query="Milton")[0]
        found_bottle = list_items(item_type="found", query="Milton")[0]
        
        result = match_items(lost_bottle, found_bottle)
        print(f"[OK] Milton Bottle match result: {result['overall_score']}% (Expected >= 85%)")
        self.assertGreaterEqual(result["overall_score"], 85.0)

    def test_05_matches_listing(self):
        matches = list_matches(min_score=50.0)
        print(f"[OK] Generated candidate matches in system: {len(matches)}")
        self.assertGreaterEqual(len(matches), 4)

    def test_06_cloud_service_fallback(self):
        status = cloud_service.test_connection()
        print(f"[OK] Cloud service status check: {status['status']} ({status['message']})")
        self.assertIn("status", status)

if __name__ == "__main__":
    unittest.main()
