#!/usr/bin/env python3
"""Talk to ClickUp from the CLI or from Claude: read a task, comment on it, set status.

Reads CLICKUP_TOKEN from the environment. Each dev uses their OWN token
(ClickUp -> Settings -> Apps -> API Token). Never commit a token.

  python pm/clickup_task.py get      <task_id>
  python pm/clickup_task.py comment  <task_id> "progress note"
  python pm/clickup_task.py status   <task_id> "in progress"
  python pm/clickup_task.py statuses <task_id>      # valid status names for this task's list

Get a task_id from its ClickUp URL (last path segment) or the task's "Copy ID".
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.clickup.com/api/v2"
TOKEN = os.environ.get("CLICKUP_TOKEN", "").strip()


def req(path, body=None, method="GET"):
    if not TOKEN:
        sys.exit("Set CLICKUP_TOKEN in your environment (ClickUp -> Settings -> Apps -> API Token).")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": TOKEN}
    if data:
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        return json.load(urllib.request.urlopen(r, timeout=30))
    except urllib.error.HTTPError as e:
        sys.exit(f"ClickUp HTTP {e.code}: {e.read().decode()[:300]}")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd, task_id = argv[0], argv[1]
    if cmd == "get":
        t = req(f"/task/{task_id}")
        print(f"{t['name']}  [{t['status']['status']}]")
        print(t.get("description") or "(no description)")
    elif cmd == "comment":
        if len(argv) < 3:
            sys.exit("need comment text")
        req(f"/task/{task_id}/comment", {"comment_text": argv[2]}, "POST")
        print("comment posted")
    elif cmd == "status":
        if len(argv) < 3:
            sys.exit("need a status name (see `statuses <task_id>`)")
        req(f"/task/{task_id}", {"status": argv[2]}, "PUT")
        print(f"status -> {argv[2]}")
    elif cmd == "statuses":
        t = req(f"/task/{task_id}")
        lst = req(f"/list/{t['list']['id']}")
        print(", ".join(s["status"] for s in lst.get("statuses", [])))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
