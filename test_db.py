"""Tests for the database layer.

Run with:  python3 -m unittest test_db -v

Each test gets its own throwaway database file, so nothing here touches the
real ``lending.db``.
"""

from __future__ import annotations

import os
import tempfile
import unittest

import data
import db
import metrics


class DatabaseTestCase(unittest.TestCase):
    """Base class: fresh, seeded database per test."""

    def setUp(self):
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(path)  # let SQLite create it, so init() sees a new file
        self._path = path
        self._original_path = db.DB_PATH
        db.close()
        db.DB_PATH = path
        metrics.reset()  # metrics are global; keep tests independent
        db.init()

    def tearDown(self):
        db.close()
        db.DB_PATH = self._original_path
        if os.path.exists(self._path):
            os.unlink(self._path)

    def garcia(self) -> dict:
        return data.find_professor_by_id_card("PROF-001")


class TestSeed(DatabaseTestCase):
    def test_seeds_expected_rows(self):
        self.assertEqual(len(data.all_items()), 3)
        self.assertEqual(len(data.all_professors()), 3)
        self.assertIsNotNone(data.find_user("admin"))
        self.assertIsNotNone(data.find_user("DGarcia"))

    def test_professor_account_resolves_to_a_name(self):
        self.assertEqual(data.find_user("DGarcia")["professor"], "Prof. García")
        self.assertEqual(data.find_user("admin")["professor"], "")

    def test_seeded_loan_reads_back_as_a_name(self):
        projector = data.find_item("2")
        self.assertEqual(projector["status"], "assigned")
        self.assertEqual(projector["assigned_to"], "Prof. García")

    def test_init_is_idempotent(self):
        db.init()
        self.assertEqual(len(data.all_professors()), 3)

    def test_unknown_user_is_none(self):
        self.assertIsNone(data.find_user("nobody"))


class TestItems(DatabaseTestCase):
    def test_add_and_find(self):
        created = data.add_item("TEST-1", "Tripod", "Peripherals", "Aluminium")
        self.assertEqual(created["name"], "Tripod")
        self.assertEqual(created["status"], "available")
        self.assertEqual(created["assigned_to"], "")
        self.assertEqual(data.find_item("TEST-1")["description"], "Aluminium")

    def test_duplicate_id_is_rejected(self):
        data.add_item("TEST-1", "Tripod", "Peripherals", "")
        self.assertIsNone(data.add_item("TEST-1", "Other", "Monitors", ""))
        self.assertEqual(len(data.all_items()), 4)

    def test_update_keeps_blank_name_and_bad_category(self):
        data.add_item("TEST-1", "Tripod", "Peripherals", "old")
        data.update_item("TEST-1", "", "Nonsense", "new")
        item = data.find_item("TEST-1")
        self.assertEqual(item["name"], "Tripod")
        self.assertEqual(item["category"], "Peripherals")
        self.assertEqual(item["description"], "new")

    def test_delete(self):
        data.add_item("TEST-1", "Tripod", "Peripherals", "")
        data.delete_item("TEST-1")
        self.assertIsNone(data.find_item("TEST-1"))

    def test_status_toggle_hides_item_from_available(self):
        data.set_item_status("1", "disabled")
        names = [i["name"] for i in data.available_items()]
        self.assertNotIn("Dell Latitude Laptop", names)
        data.set_item_status("1", "available")
        self.assertIsNotNone(data.find_available_item_by_name("Dell Latitude Laptop"))

    def test_assigned_item_is_not_available(self):
        self.assertIsNone(data.find_available_item_by_name("Epson Projector"))


class TestLending(DatabaseTestCase):
    def test_assign_then_return_round_trip(self):
        prof = self.garcia()
        data.assign_item("1", prof["id"], "2026-07-28", "2026-08-15")

        item = data.find_item("1")
        self.assertEqual(item["status"], "assigned")
        self.assertEqual(item["assigned_to"], "Prof. García")
        self.assertEqual(item["assigned_on"], "2026-07-28")
        self.assertEqual(item["due_date"], "2026-08-15")

        data.return_item("1")
        item = data.find_item("1")
        self.assertEqual(item["status"], "available")
        self.assertEqual(item["assigned_to"], "")
        self.assertEqual(item["assigned_on"], "")
        self.assertEqual(item["due_date"], "")

    def test_active_item_count_and_list(self):
        prof = self.garcia()
        self.assertEqual(data.professor_active_item_count(prof["id"]), 1)
        data.assign_item("1", prof["id"], "2026-07-28", "2026-08-15")
        self.assertEqual(data.professor_active_item_count(prof["id"]), 2)
        names = [i["name"] for i in data.items_assigned_to(prof["id"])]
        self.assertCountEqual(names, ["Epson Projector", "Dell Latitude Laptop"])

    def test_is_overdue(self):
        prof = self.garcia()
        data.assign_item("1", prof["id"], "2020-01-01", "2020-01-02")
        self.assertTrue(data.is_overdue(data.find_item("1")))
        self.assertFalse(data.is_overdue(data.find_item("3")))


class TestProfessors(DatabaseTestCase):
    def test_add_and_find_by_card(self):
        created = data.add_professor("Prof. Mora", "Law", "PROF-100")
        self.assertEqual(created["name"], "Prof. Mora")
        self.assertEqual(data.find_professor_by_id_card("PROF-100")["id"], created["id"])
        self.assertEqual(data.find_professor(created["id"])["department"], "Law")

    def test_duplicate_id_card_is_rejected(self):
        self.assertIsNone(data.add_professor("Impostor", "Law", "PROF-001"))
        self.assertEqual(len(data.all_professors()), 3)

    def test_rename_updates_their_loans(self):
        prof = self.garcia()
        self.assertTrue(
            data.update_professor(prof["id"], "PROF-001", "Prof. García Mora", "Engineering")
        )
        # The loan followed the rename instead of being orphaned.
        self.assertEqual(data.find_item("2")["assigned_to"], "Prof. García Mora")

    def test_update_to_a_taken_id_card_is_refused(self):
        prof = self.garcia()
        self.assertFalse(
            data.update_professor(prof["id"], "PROF-002", "Prof. García", "Engineering")
        )
        self.assertEqual(data.find_professor(prof["id"])["id_card"], "PROF-001")

    def test_delete_is_refused_while_holding_an_item(self):
        prof = self.garcia()
        self.assertFalse(data.delete_professor(prof["id"]))
        self.assertIsNotNone(data.find_professor(prof["id"]))

    def test_delete_succeeds_once_items_are_returned(self):
        prof = self.garcia()
        data.return_item("2")
        self.assertTrue(data.delete_professor(prof["id"]))
        self.assertIsNone(data.find_professor(prof["id"]))

    def test_deleting_a_professor_leaves_their_account_usable(self):
        prof = self.garcia()
        data.return_item("2")
        data.delete_professor(prof["id"])
        # ON DELETE SET NULL: the account survives with no professor attached.
        account = data.find_user("DGarcia")
        self.assertIsNotNone(account)
        self.assertEqual(account["professor"], "")


class TestMetrics(DatabaseTestCase):
    @staticmethod
    def row(snap: dict, group: str, name: str):
        for entry in snap["groups"][group]:
            if entry["name"] == name:
                return entry
        return None

    def test_data_calls_are_recorded_per_function(self):
        data.all_items()
        data.all_items()
        data.find_user("admin")

        snap = metrics.snapshot()
        self.assertEqual(self.row(snap, "function", "all_items")["count"], 2)
        self.assertEqual(self.row(snap, "function", "find_user")["count"], 1)

    def test_sql_statements_are_labelled_by_verb_and_table(self):
        data.all_professors()
        data.add_professor("Prof. Mora", "Law", "PROF-100")

        snap = metrics.snapshot()
        self.assertIsNotNone(self.row(snap, "query", "SELECT professors"))
        self.assertIsNotNone(self.row(snap, "query", "INSERT professors"))

    def test_lock_wait_is_recorded(self):
        data.all_items()
        wait = self.row(metrics.snapshot(), "query", "_lock wait")
        self.assertIsNotNone(wait)
        self.assertGreaterEqual(wait["count"], 1)

    def test_connection_open_is_timed(self):
        # setUp already opened one connection via db.init().
        self.assertEqual(metrics.snapshot()["connection"]["count"], 1)

    def test_percentiles_are_ordered(self):
        for value in range(1, 101):
            metrics.record("request", "GET /fake", value / 1000)
        row = self.row(metrics.snapshot(), "request", "GET /fake")
        self.assertEqual(row["count"], 100)
        self.assertLessEqual(row["p50_ms"], row["p95_ms"])
        self.assertLessEqual(row["p95_ms"], row["p99_ms"])
        self.assertLessEqual(row["p99_ms"], row["max_ms"])
        self.assertAlmostEqual(row["max_ms"], 100.0, places=6)

    def test_timed_decorator_records_under_a_custom_name(self):
        @metrics.timed("function", "custom_label")
        def work():
            return 42

        self.assertEqual(work(), 42)
        self.assertEqual(self.row(metrics.snapshot(), "function", "custom_label")["count"], 1)

    def test_timed_records_even_when_the_call_raises(self):
        @metrics.timed("function", "boom")
        def work():
            raise ValueError("nope")

        with self.assertRaises(ValueError):
            work()
        self.assertEqual(self.row(metrics.snapshot(), "function", "boom")["count"], 1)

    def test_reset_clears_everything(self):
        data.all_items()
        metrics.reset()
        snap = metrics.snapshot()
        self.assertEqual(snap["groups"]["function"], [])
        self.assertEqual(snap["groups"]["query"], [])
        self.assertEqual(snap["connection"]["count"], 0)
        self.assertEqual(snap["lock"]["peak_waiting"], 0)

    def test_concurrent_calls_raise_peak_waiting(self):
        import threading

        def hammer():
            for _ in range(40):
                data.all_items()

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        snap = metrics.snapshot()
        self.assertGreater(snap["lock"]["peak_waiting"], 1)
        self.assertEqual(snap["lock"]["waiting_now"], 0)
        self.assertEqual(self.row(snap, "function", "all_items")["count"], 320)


class TestValidation(DatabaseTestCase):
    def test_item_id_rules(self):
        self.assertTrue(data.valid_item_id("AB-12_x"))
        self.assertFalse(data.valid_item_id(""))
        self.assertFalse(data.valid_item_id("has space"))

    def test_id_card_rules(self):
        self.assertTrue(data.valid_id_card("PROF-001"))
        self.assertFalse(data.valid_id_card("PROF 001"))


if __name__ == "__main__":
    unittest.main()
