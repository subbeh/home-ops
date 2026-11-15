"""The morning-brief skill's GitHub lines (docs/services/hermes/profiles.md#cron-jobs).

Prints the user's open GitHub PRs, authored or assigned, each with its
draft, review, checks and conflict state. Then the issues they created or are assigned to that
someone else commented on, closed or reopened in the last 24 hours. The brief copies both. It
reads GitHub's GraphQL search with default's read-only GITHUB_ACTIONS_TOKEN. It always exits 0
and says when GitHub can't be read, so the brief still posts.
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.github.com/graphql"
DATA = Path(__file__).resolve().parent.parent
PR_ROLES = {"yours": "author:@me", "assigned": "assignee:@me"}
ISSUE_ROLES = {"yours": "author:@me", "assigned": "assignee:@me"}
PR_FIELDS = "... on PullRequest { url number title isDraft reviewDecision mergeable repository { nameWithOwner } commits(last: 1) { nodes { commit { statusCheckRollup { state } } } } }"
# Who acted and when; the last 20 cover a day's activity on one issue.
ISSUE_FIELDS = (
    "... on Issue { url number title repository { nameWithOwner } comments(last: 20) { nodes { author { login } createdAt } }"
    " timelineItems(last: 20, itemTypes: [CLOSED_EVENT, REOPENED_EVENT]) { nodes { __typename"
    " ... on ClosedEvent { actor { login } createdAt } ... on ReopenedEvent { actor { login } createdAt } } } }"
)
REVIEW = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes requested"}
CHECKS = {"SUCCESS": "passing", "FAILURE": "failing", "ERROR": "failing", "PENDING": "pending", "EXPECTED": "pending"}
EVENTS = {"ClosedEvent": "closed", "ReopenedEvent": "reopened"}


def query(since):
    # shortcut: 50 per search, no paging; page once someone has more.
    def search(alias, q, fields):
        return f'{alias}: search(type: ISSUE, first: 50, query: "{q} sort:updated-desc") {{ nodes {{ {fields} }} }}'

    parts = [search(f"p{i}", f"is:pr is:open archived:false {q}", PR_FIELDS) for i, q in enumerate(PR_ROLES.values())]
    parts += [search(f"i{i}", f"is:issue updated:>={since} {q}", ISSUE_FIELDS) for i, q in enumerate(ISSUE_ROLES.values())]
    return "{ viewer { login } " + " ".join(parts) + " }"


def fetch(token, since):
    req = urllib.request.Request(API, data=json.dumps({"query": query(since)}).encode(), headers={"Authorization": f"Bearer {token}", "User-Agent": "hermes-github-updates"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    # GraphQL errors come with a 200; a node the token can't read comes back null beside them.
    if not body.get("data"):
        raise RuntimeError(body["errors"][0].get("message"))
    return body["data"], [e.get("message", "") for e in body.get("errors", [])]


def error_lines(errors):
    # One line per distinct reason, e.g. an org that refuses tokens living over 366 days.
    reasons = dict.fromkeys(m.split(". ")[0] for m in errors)
    return [f"GitHub: {len(errors)} PRs or issues couldn't be read: {r}." for r in reasons]


def merged(data, prefix, roles):
    items = {}
    for i, role in enumerate(roles):
        for item in filter(None, data[f"{prefix}{i}"]["nodes"]):
            items.setdefault(item["url"], (item, []))[1].append(role)
    return items.values()


def pr_lines(data):
    prs = list(merged(data, "p", PR_ROLES))
    if not prs:
        return ["Open GitHub PRs: none."]
    lines = [f"Open GitHub PRs ({len(prs)}):"]
    for pr, roles in prs:
        commits = pr["commits"]["nodes"]
        rollup = commits and commits[0]["commit"]["statusCheckRollup"]
        state = ["draft"] if pr["isDraft"] else []
        state.append("review: " + REVIEW.get(pr["reviewDecision"], "waiting"))
        state.append("checks: " + (CHECKS.get(rollup["state"], "pending") if rollup else "none"))
        if pr["mergeable"] == "CONFLICTING":
            state.append("merge conflicts")
        lines.append(f"- {pr['repository']['nameWithOwner']}#{pr['number']} {pr['title']} ({', '.join(roles)}) {pr['url']}: {'; '.join(state)}")
    return lines


def login(node, key):
    return (node.get(key) or {}).get("login", "ghost")  # deleted accounts come back as null


def issue_lines(data, since):
    me, lines = data["viewer"]["login"], []
    for issue, roles in merged(data, "i", ISSUE_ROLES):
        comments = [login(c, "author") for c in issue["comments"]["nodes"] if c["createdAt"] >= since and login(c, "author") != me]
        events = [f"{EVENTS[e['__typename']]} by {login(e, 'actor')}" for e in issue["timelineItems"]["nodes"] if e["createdAt"] >= since and login(e, "actor") != me]
        if comments:
            events.insert(0, f"{len(comments)} new comment{'s' * (len(comments) > 1)} from {', '.join(dict.fromkeys(comments))}")
        if events:
            lines.append(f"- {issue['repository']['nameWithOwner']}#{issue['number']} {issue['title']} ({', '.join(roles)}) {issue['url']}: {'; '.join(events)}")
    return [f"GitHub issues with updates since yesterday ({len(lines)}):", *lines] if lines else ["GitHub issues with updates since yesterday: none."]


def main():
    try:
        env = dict(l.strip().split("=", 1) for l in (DATA / ".env").read_text().splitlines() if "=" in l and l[0] != "#")
        since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        data, errors = fetch(env["GITHUB_ACTIONS_TOKEN"].strip('"'), since)
        print("\n".join(pr_lines(data) + issue_lines(data, since) + error_lines(errors)))
    except Exception as e:  # any failure, a bad token included: the brief posts without GitHub
        print(f"GitHub unavailable: PRs and issues couldn't be read ({type(e).__name__}).")


if __name__ == "__main__":
    main()
