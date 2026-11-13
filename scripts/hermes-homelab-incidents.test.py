#!/usr/bin/env python3
# Self-test for the hermes homelab-incidents pre-check: the down threshold and once-per-incident wakes.
# Run with `just docs-test`.
import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

# Keep __pycache__ out of the dir Ansible ships from.
sys.dont_write_bytecode = True

_path = pathlib.Path(__file__).resolve().parent.parent / "ansible/services/data/hermes/homelab-incidents.py"
_spec = importlib.util.spec_from_file_location("homelab_incidents", _path)
incidents = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(incidents)

OK = {"success": True, "timestamp": "t0"}


def failing(n):
    return [{"success": False, "timestamp": f"t{i}", "errors": ["timeout"],
             "conditionResults": [{"condition": "[STATUS] (502) == 200", "success": False}]} for i in range(1, n + 1)]


class Down(unittest.TestCase):
    def test_threshold(self):
        out = incidents.down([
            {"key": "services_a", "name": "a", "group": "services", "results": [OK] + failing(3)},
            {"key": "services_b", "results": [OK] + failing(2)},
            {"key": "services_c", "results": failing(3) + [OK]},
            {"key": "backups_d", "results": None},
        ])
        self.assertEqual(list(out), ["services_a"])
        self.assertEqual(out["services_a"]["failing_since"], "t1")
        self.assertEqual(out["services_a"]["failed_conditions"], ["[STATUS] (502) == 200"])


class Main(unittest.TestCase):
    def run_main(self, statuses):
        stdout = io.StringIO()
        resp = mock.MagicMock()
        resp.__enter__.return_value = io.StringIO(json.dumps(statuses))
        with mock.patch.object(incidents.urllib.request, "urlopen", return_value=resp), contextlib.redirect_stdout(stdout):
            incidents.main()
        return stdout.getvalue().splitlines()

    def test_once_per_incident(self):
        with tempfile.TemporaryDirectory() as d:
            incidents.DOWN = pathlib.Path(d) / "down.json"
            down = [{"key": "services_a", "results": failing(3)}]
            first = self.run_main(down)
            self.assertIn("## services_a", first)
            self.assertEqual(first[-1], '{"wakeAgent": true}')
            self.assertEqual(self.run_main(down), ['{"wakeAgent": false}'])
            self.assertEqual(self.run_main([{"key": "services_a", "results": [OK]}]), ['{"wakeAgent": false}'])
            self.assertEqual(self.run_main(down)[-1], '{"wakeAgent": true}')

    def test_gatus_unreachable_wakes_once(self):
        with tempfile.TemporaryDirectory() as d:
            incidents.DOWN = pathlib.Path(d) / "down.json"
            with mock.patch.object(incidents.urllib.request, "urlopen", side_effect=OSError("refused")):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    incidents.main()
                    incidents.main()
            lines = out.getvalue().splitlines()
            self.assertEqual(lines.count('{"wakeAgent": true}'), 1)
            self.assertEqual(lines[-1], '{"wakeAgent": false}')


if __name__ == "__main__":
    unittest.main()
