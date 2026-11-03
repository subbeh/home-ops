#!/usr/bin/env python3
# Self-test for the hermes homelab plugin's response parsing. Run with `just docs-test`.
import importlib.util
import json
import pathlib
import sys
import unittest

# The plugin dir is copied to the vps as-is, so keep __pycache__ out of it.
sys.dont_write_bytecode = True
_path = pathlib.Path(__file__).resolve().parent.parent / "ansible/services/data/hermes/homelab/__init__.py"
_spec = importlib.util.spec_from_file_location("homelab", _path)
homelab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(homelab)


def frame(stream, text):
    data = text.encode()
    return bytes([stream, 0, 0, 0]) + len(data).to_bytes(4, "big") + data


class Status(unittest.TestCase):
    def test_down_first_with_last_failure(self):
        endpoints = [
            {"key": "services_atuin", "results": [
                {"success": True, "timestamp": "t1"}]},
            {"key": "services_hermes", "results": [
                {"success": False, "timestamp": "t1", "conditionResults": [
                    {"condition": "[STATUS] (502) == 200", "success": False},
                    {"condition": "[RESPONSE_TIME] < 500", "success": True}]},
                {"success": False, "timestamp": "t2", "errors": ["timeout"]}]},
            {"key": "backups_restic-backup", "results": None},
        ]
        out = homelab.summarize_statuses(endpoints)
        self.assertEqual([e["key"] for e in out], ["services_hermes", "backups_restic-backup", "services_atuin"])
        self.assertEqual(out[0]["recent"], "0/2 ok")
        self.assertEqual(out[0]["last_failure"], {"at": "t2", "errors": ["timeout"], "failed_conditions": []})
        self.assertIsNone(out[1]["up"])
        self.assertNotIn("last_failure", out[2])


class Semaphore(unittest.TestCase):
    def test_tasks_newest_first(self):
        tasks = [{"id": 1, "status": "error", "params": {"tags": ["gatus"]}, "commit_hash": "abcdef123"},
                 {"id": 3, "status": "success", "params": None},
                 {"id": 2, "status": "success"}]
        out = homelab.summarize_tasks(tasks, 2)
        self.assertEqual([t["id"] for t in out], [3, 2])
        self.assertIsNone(out[0]["tags"])
        self.assertEqual(homelab.summarize_tasks(tasks, 5)[2]["commit"], "abcdef1")

    def test_output_tail_strips_colour(self):
        rows = [{"output": "one"}, {"output": "\x1b[0;32mok: [vps]\x1b[0m"}, {"output": None}]
        self.assertEqual(homelab.tail_output(rows, 2), "ok: [vps]\n")


class Docker(unittest.TestCase):
    def test_containers(self):
        out = homelab.summarize_containers([{"Names": ["/traefik"], "State": "running"}, {"Names": ["/aven"]}])
        self.assertEqual([c["name"] for c in out], ["aven", "traefik"])

    def test_logs_framed_and_raw(self):
        self.assertEqual(homelab.demux_logs(frame(1, "out\n") + frame(2, "err\n")), "out\nerr\n")
        self.assertEqual(homelab.demux_logs(b"tty line\n"), "tty line\n")
        self.assertEqual(homelab.demux_logs(b""), "")

    def test_bad_name_refused_before_any_request(self):
        out = json.loads(homelab.container_logs({"name": "../info"}))
        self.assertIn("not a container name", out["error"])


if __name__ == "__main__":
    unittest.main()
