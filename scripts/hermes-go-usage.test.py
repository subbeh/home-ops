#!/usr/bin/env python3
# Self-test for the hermes go-usage pre-check script's report. Run with `just docs-test`.
import importlib.util
import pathlib
import sys
import unittest

# The script's dir is copied to the vps as-is, so keep __pycache__ out of it.
sys.dont_write_bytecode = True
_path = pathlib.Path(__file__).resolve().parent.parent / "ansible/services/data/hermes/go-usage.py"
_spec = importlib.util.spec_from_file_location("go_usage", _path)
gu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gu)


def meter(used, limit):
    return {"usedMicroCents": str(int(used * 1e8)), "limitMicroCents": str(int(limit * 1e8)), "resetsAt": "2026-11-16T00:00:00.000Z"}


def status(five=1, week=10, month=10):
    return {"product": "go-plus", "access": {"meters": {"fiveHour": meter(five, 48), "week": meter(week, 120), "month": meter(month, 240)}}}


def model(name, cost):
    return {"model": name, "totalCostMicroCents": str(int(cost * 1e8))}


class Report(unittest.TestCase):
    def test_meters_and_models(self):
        out = gu.report(status(week=60), [model("kimi-k3.1-pro", 13.05)])
        self.assertIn("- Week: $60.00 of $120 (50%), resets Mon 16 Nov", out)
        self.assertIn("- kimi-k3.1-pro: $13.05 of $60 (22%)", out)
        self.assertNotIn("5 hours", out)
        self.assertNotIn("⚠", out)

    def test_flags_over_75_percent(self):
        out = gu.report(status(five=40, week=100), [model("kimi-k3.1-pro", 50)])
        self.assertIn("- 5 hours: $40.00 of $48 (83%)", out)
        self.assertEqual(out.count("⚠ over 75%"), 3)

    def test_unknown_model_and_no_usage(self):
        self.assertIn("- new-model: $1.00 (allowance not in go-usage.py)", gu.report(status(), [model("new-model", 1)]))
        self.assertIn("- No usage yet.", gu.report(status(), []))

    def test_unreachable_still_prints(self):
        gu.DATA = pathlib.Path(__file__).resolve().parent  # no .env here, so main() fails before any request
        from io import StringIO
        from contextlib import redirect_stdout

        buf = StringIO()
        with redirect_stdout(buf):
            gu.main()
        self.assertIn("OpenCode Go usage unavailable", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
