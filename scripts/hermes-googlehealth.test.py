#!/usr/bin/env python3
# Self-test for the hermes googlehealth plugin's date handling and response parsing. Run with `just docs-test`.
import datetime
import importlib.util
import json
import pathlib
import sys
import unittest

# The plugin dir is copied to the vps as-is, so keep __pycache__ out of it.
sys.dont_write_bytecode = True
_path = pathlib.Path(__file__).resolve().parent.parent / "ansible/services/data/hermes/googlehealth/__init__.py"
_spec = importlib.util.spec_from_file_location("googlehealth", _path)
gh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gh)

D = datetime.date


class Dates(unittest.TestCase):
    def test_end_inclusive_and_defaults_to_start(self):
        self.assertEqual(gh.date_range({"start_date": "2026-11-01", "end_date": "2026-11-14"}, 14),
                         (D(2026, 11, 1), D(2026, 11, 15)))
        self.assertEqual(gh.date_range({"start_date": "2026-11-01"}, 1), (D(2026, 11, 1), D(2026, 11, 2)))

    def test_refuses_bad_input(self):
        for params in ({"start_date": "2026-11-01", "end_date": "2026-11-15"},  # 15 days
                       {"start_date": "2026-11-02", "end_date": "2026-11-01"},
                       {"start_date": '2026-11-01" OR x >= "0'},
                       {}):
            with self.assertRaises(ValueError):
                gh.date_range(params, 14)

    def test_filter(self):
        self.assertEqual(gh.record_filter("sleep.interval.civil_end_time", D(2026, 3, 4), D(2026, 3, 5)),
                         'sleep.interval.civil_end_time >= "2026-03-04" AND sleep.interval.civil_end_time < "2026-03-05"')


class Parsing(unittest.TestCase):
    def test_rollup(self):
        points = [{"civilStartTime": {"date": {"year": 2026, "month": 7, "day": 28}},
                   "civilEndTime": {"date": {"year": 2026, "month": 7, "day": 29}},
                   "steps": {"countSum": "8430"}}]
        self.assertEqual(gh.summarize_rollup(points), [{"date": "2026-07-28", "countSum": "8430"}])

    def test_trim_drops_stages(self):
        point = {"sleep": {"stages": [{"type": "DEEP"}], "summary": {"minutesAsleep": "420"}}}
        self.assertEqual(gh.trim([point]), [{"sleep": {"summary": {"minutesAsleep": "420"}}}])


class Tools(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._api = gh._api

    def tearDown(self):
        gh._api = self._api

    def test_records_follows_pages(self):
        pages = [{"dataPoints": [{"sleep": {"summary": {}}}], "nextPageToken": "p2"},
                 {"dataPoints": [{"sleep": {"summary": {}}}]}]

        def api(path, query=None, body=None):
            self.calls.append((path, dict(query)))
            return pages[len(self.calls) - 1]
        gh._api = api
        out = json.loads(gh.records({"data_type": "sleep", "start_date": "2026-11-01", "end_date": "2026-11-07"}))
        self.assertEqual(len(out["records"]), 2)
        self.assertEqual(self.calls[0][0], "dataTypes/sleep/dataPoints:reconcile")
        self.assertEqual(self.calls[1][1]["pageToken"], "p2")

    def test_daily_body_and_unknown_type(self):
        def api(path, query=None, body=None):
            self.calls.append((path, body))
            return {"rollupDataPoints": []}
        gh._api = api
        gh.daily({"data_type": "steps", "start_date": "2026-07-28", "end_date": "2026-07-29"})
        path, body = self.calls[0]
        self.assertEqual(path, "dataTypes/steps/dataPoints:dailyRollUp")
        self.assertEqual(body["range"]["end"]["date"], {"year": 2026, "month": 7, "day": 30})
        self.assertIn("error", json.loads(gh.daily({"data_type": "sleep", "start_date": "2026-07-28"})))


if __name__ == "__main__":
    unittest.main()
