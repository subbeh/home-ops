#!/usr/bin/env python3
# Self-test for the hermes quota-alerts cron script's notice rules. Run with `just docs-test`.
import importlib.util
import pathlib
import sqlite3
import sys
import unittest
from collections import Counter

# The script's dir is copied to the vps as-is, so keep __pycache__ out of it.
sys.dont_write_bytecode = True
_path = pathlib.Path(__file__).resolve().parent.parent / "ansible/services/data/hermes/quota-alerts.py"
_spec = importlib.util.spec_from_file_location("quota_alerts", _path)
qa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qa)

THREAD = "111"


def board():
    db = sqlite3.connect(":memory:")
    db.executescript(
        """CREATE TABLE tasks (id TEXT, title TEXT, assignee TEXT, status TEXT, model_override TEXT);
           CREATE TABLE task_runs (id INTEGER PRIMARY KEY, task_id TEXT, status TEXT, started_at INT, ended_at INT);
           CREATE TABLE kanban_notify_subs (task_id TEXT, platform TEXT, chat_id TEXT, thread_id TEXT);"""
    )
    return db


def card(db, id, status="ready", assignee="reviewer", thread=THREAD, runs=()):
    db.execute("INSERT INTO tasks VALUES (?, ?, ?, ?, 'some-model')", (id, f"Title {id}", assignee, status))
    if thread:
        db.execute("INSERT INTO kanban_notify_subs VALUES (?, 'discord', ?, ?)", (id, thread, thread))
    for r in runs:
        add_run(db, id, r)


def add_run(db, id, status):
    ended = None if status == "running" else 2000
    db.execute("INSERT INTO task_runs (task_id, status, started_at, ended_at) VALUES (?, ?, 1000, ?)", (id, status, ended))


class Base(unittest.TestCase):
    def setUp(self):
        self.posts = []
        self.seen = {"cards": [], "rounds": {}, "spend": False}
        orig_post = qa.post
        qa.post = lambda target, text: self.posts.append((target, text))
        self.addCleanup(setattr, qa, "post", orig_post)


RL = "rate_limited"


class Stuck(Base):
    def test_three_limited_runs_alert_once_in_the_goal_thread(self):
        db = board()
        card(db, "a", runs=[RL, RL, RL])
        qa.check_stuck(db, self.seen)
        qa.check_stuck(db, self.seen)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.posts[0][0], f"discord:{THREAD}")
        self.assertIn("some-model", self.posts[0][1])

    def test_two_limited_runs_stay_quiet(self):
        db = board()
        card(db, "a", runs=["done", RL, RL])
        qa.check_stuck(db, self.seen)
        self.assertEqual(self.posts, [])

    def test_run_in_progress_does_not_end_the_spell(self):
        db = board()
        card(db, "a", runs=[RL, RL, RL])
        qa.check_stuck(db, self.seen)
        add_run(db, "a", "running")
        qa.check_stuck(db, self.seen)
        self.assertEqual(len(self.posts), 1)

    def test_normal_run_starts_a_new_spell(self):
        db = board()
        card(db, "a", runs=[RL, RL, RL])
        qa.check_stuck(db, self.seen)
        add_run(db, "a", "done")
        qa.check_stuck(db, self.seen)
        for _ in range(3):
            add_run(db, "a", RL)
        qa.check_stuck(db, self.seen)
        self.assertEqual(len(self.posts), 2)

    def test_finished_card_is_ignored(self):
        db = board()
        card(db, "a", status="done", runs=[RL, RL, RL])
        qa.check_stuck(db, self.seen)
        self.assertEqual(self.posts, [])

    def test_no_thread_goes_to_the_home_channel(self):
        db = board()
        card(db, "a", thread=None, runs=[RL, RL, RL])
        qa.check_stuck(db, self.seen)
        self.assertEqual(self.posts[0][0], qa.HOME_CHANNEL)

    def test_title_cannot_ping_everyone(self):
        db = board()
        card(db, "a", runs=[RL, RL, RL])
        db.execute("UPDATE tasks SET title = 'hi @everyone'")
        qa.check_stuck(db, self.seen)
        self.assertNotIn("@everyone", self.posts[0][1])

    def test_failed_post_is_retried_but_sent_ones_are_not(self):
        db = board()
        card(db, "a", runs=[RL, RL, RL])
        card(db, "b", runs=[RL, RL, RL])
        def fail_on_b(target, text):
            if "Card b" in text:
                raise SystemExit("send failed")
            self.posts.append((target, text))
        qa.post = fail_on_b
        with self.assertRaises(SystemExit):
            qa.check_stuck(db, self.seen)
        self.assertEqual(self.seen["cards"], ["a"])


class Rounds(Base):
    def test_notices_every_round_from_the_third(self):
        db = board()
        card(db, "r1", status="done")
        card(db, "r2", status="done")
        qa.check_rounds(db, self.seen)
        self.assertEqual(self.posts, [])
        card(db, "r3")
        qa.check_rounds(db, self.seen)
        qa.check_rounds(db, self.seen)
        self.assertEqual(len(self.posts), 1)
        self.assertIn("round 3", self.posts[0][1])
        card(db, "r4")
        qa.check_rounds(db, self.seen)
        self.assertIn("round 4", self.posts[1][1])
        self.assertEqual(self.posts[1][0], f"discord:{THREAD}")

    def test_closed_goal_stays_quiet(self):
        db = board()
        for id in ("r1", "r2", "r3"):
            card(db, id, status="done")
        qa.check_rounds(db, self.seen)
        self.assertEqual(self.posts, [])

    def test_other_profiles_do_not_count(self):
        db = board()
        for id in ("w1", "w2", "w3"):
            card(db, id, assignee="writer")
        qa.check_rounds(db, self.seen)
        self.assertEqual(self.posts, [])


class Spend(Base):
    def spending(self, value):
        orig = qa.hourly_spend
        qa.hourly_spend = lambda: value
        self.addCleanup(setattr, qa, "hourly_spend", orig)

    def test_one_notice_per_spike_then_rearms(self):
        self.spending(Counter({"kimi": 7.0}))
        qa.check_spend(self.seen)
        qa.check_spend(self.seen)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.posts[0][0], qa.HOME_CHANNEL)
        self.assertIn("kimi $7.00", self.posts[0][1])
        qa.hourly_spend = lambda: Counter({"kimi": 1.0})
        qa.check_spend(self.seen)
        qa.hourly_spend = lambda: Counter({"kimi": 7.0})
        qa.check_spend(self.seen)
        self.assertEqual(len(self.posts), 2)

    def test_only_opencode_go_counts(self):
        observations = [
            {"model": "kimi", "totalCost": 2.0, "metadata": {"provider": "opencode-go"}},
            {"model": "kimi", "totalCost": None, "metadata": {"provider": "opencode-go"}},
            {"model": "claude-opus", "totalCost": 9.0, "metadata": {"speed": "standard"}},
            {"model": "other", "totalCost": 9.0, "metadata": None},
        ]
        self.assertEqual(qa.go_spend(observations), Counter({"kimi": 2.0}))

    def test_quiet_under_the_limit(self):
        self.spending(Counter({"kimi": qa.SPEND_LIMIT}))
        qa.check_spend(self.seen)
        self.assertEqual(self.posts, [])

    def test_langfuse_down_keeps_the_state(self):
        self.seen["spend"] = True
        self.spending(None)
        qa.check_spend(self.seen)
        self.assertTrue(self.seen["spend"])
        self.assertEqual(self.posts, [])


if __name__ == "__main__":
    unittest.main()
