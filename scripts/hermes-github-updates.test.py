#!/usr/bin/env python3
# Self-test for the hermes github-updates script's report. Run with `just docs-test`.
import importlib.util
import pathlib
import sys
import unittest

# The script's dir is copied to the vps as-is, so keep __pycache__ out of it.
sys.dont_write_bytecode = True
_path = pathlib.Path(__file__).resolve().parent.parent / "ansible/services/data/hermes/github-updates.py"
_spec = importlib.util.spec_from_file_location("github_updates", _path)
gu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gu)

SINCE = "2026-11-15T06:00:00Z"
NEW, OLD = "2026-11-15T20:00:00Z", "2026-11-14T20:00:00Z"


def pr(n, draft=False, review=None, checks="SUCCESS", mergeable="MERGEABLE"):
    commits = [{"commit": {"statusCheckRollup": checks and {"state": checks}}}]
    return {"url": f"https://github.com/o/r/pull/{n}", "number": n, "title": f"PR {n}", "isDraft": draft, "reviewDecision": review,
            "mergeable": mergeable, "repository": {"nameWithOwner": "o/r"}, "commits": {"nodes": commits}}


def issue(n, comments=(), events=()):
    return {"url": f"https://github.com/o/r/issues/{n}", "number": n, "title": f"Issue {n}", "repository": {"nameWithOwner": "o/r"},
            "comments": {"nodes": [{"author": who and {"login": who}, "createdAt": at} for who, at in comments]},
            "timelineItems": {"nodes": [{"__typename": t, "actor": {"login": who}, "createdAt": at} for t, who, at in events]}}


def data(review=(), author=(), assignee=(), issues_author=(), issues_assignee=()):
    out = {f"p{i}": {"nodes": list(n)} for i, n in enumerate([review, author, assignee])}
    out.update({f"i{i}": {"nodes": list(n)} for i, n in enumerate([issues_author, issues_assignee])})
    out["viewer"] = {"login": "me"}
    return out


class PRs(unittest.TestCase):
    def test_none(self):
        self.assertEqual(gu.pr_lines(data()), ["Open GitHub PRs: none."])

    def test_states(self):
        out = "\n".join(gu.pr_lines(data(author=[pr(1, draft=True, review="CHANGES_REQUESTED", checks="FAILURE", mergeable="CONFLICTING"), pr(2, review="APPROVED", checks=None)])))
        self.assertIn("Open GitHub PRs (2):", out)
        self.assertIn("- o/r#1 PR 1 (yours) https://github.com/o/r/pull/1: draft; review: changes requested; checks: failing; merge conflicts", out)
        self.assertIn("- o/r#2 PR 2 (yours) https://github.com/o/r/pull/2: review: approved; checks: none", out)

    def test_waiting_and_pending(self):
        out = "\n".join(gu.pr_lines(data(review=[pr(3, review="REVIEW_REQUIRED", checks="PENDING", mergeable="UNKNOWN")])))
        self.assertIn("(review requested) https://github.com/o/r/pull/3: review: waiting; checks: pending", out)

    def test_merges_roles(self):
        out = "\n".join(gu.pr_lines(data(author=[pr(4)], assignee=[pr(4)])))
        self.assertIn("Open GitHub PRs (1):", out)
        self.assertIn("(yours, assigned)", out)


class Issues(unittest.TestCase):
    def test_none(self):
        self.assertEqual(gu.issue_lines(data(), SINCE), ["GitHub issues with updates since yesterday: none."])

    def test_others_activity(self):
        i = issue(5, comments=[("al", NEW), ("bo", NEW), ("al", NEW), ("me", NEW), ("cy", OLD)], events=[("ClosedEvent", "dee", NEW)])
        out = gu.issue_lines(data(issues_author=[i], issues_assignee=[i]), SINCE)
        self.assertEqual(out[0], "GitHub issues with updates since yesterday (1):")
        self.assertEqual(out[1], "- o/r#5 Issue 5 (yours, assigned) https://github.com/o/r/issues/5: 3 new comments from al, bo; closed by dee")

    def test_skips_own_and_old_activity(self):
        i = issue(6, comments=[("me", NEW), ("cy", OLD)], events=[("ReopenedEvent", "me", NEW)])
        self.assertEqual(gu.issue_lines(data(issues_assignee=[i]), SINCE), ["GitHub issues with updates since yesterday: none."])

    def test_deleted_author(self):
        out = gu.issue_lines(data(issues_author=[issue(7, comments=[(None, NEW)])]), SINCE)
        self.assertIn("1 new comment from ghost", out[1])


class Query(unittest.TestCase):
    def test_searches(self):
        q = gu.query(SINCE)
        self.assertEqual(q.count("search("), 5)
        self.assertIn(f"is:issue updated:>={SINCE} author:@me", q)


if __name__ == "__main__":
    unittest.main()
