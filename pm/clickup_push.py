#!/usr/bin/env python3
"""Push pm/clickup_tasks.csv into ClickUp as a List of tasks.

Usage:
    CLICKUP_TOKEN=pk_xxx python3 pm/clickup_push.py

No secret is stored in this file. Idempotent on the List name (reuses if present),
but re-running will create duplicate tasks, so run once. Folds Workstream / Estimate /
Depends On into the task description and adds the workstream as a tag for grouping.
"""
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.clickup.com/api/v2"
TOKEN = os.environ.get("CLICKUP_TOKEN", "").strip()
if not TOKEN:
    sys.exit("Set CLICKUP_TOKEN in the environment.")
LIST_NAME = "Sisense -> ThoughtSpot (Demo 2026-06-26)"
PRIORITY = {"Urgent": 1, "High": 2, "Normal": 3, "Low": 4}
NAME2EMAIL = {
    "Anuj Seth": "anuj.seth@thoughtspot.com",
    "Pooja Kalyani": "pooja.kalyani@thoughtspot.com",
    "Apratim": "apratim.medhi@thoughtspot.com",
}


def _req(path, body=None, method="GET"):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": TOKEN}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()[:300]}", file=sys.stderr)
        return None


def due_ms(date_str):
    if not date_str:
        return None
    d = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


def main():
    team = _req("/team")["teams"][0]
    space = _req(f"/team/{team['id']}/space?archived=false")["spaces"][0]
    members = {m["user"]["email"].lower(): m["user"]["id"]
               for m in team.get("members", []) if m["user"].get("email")}
    print(f"Workspace: {team['name']} | Space: {space['name']}")

    lists = (_req(f"/space/{space['id']}/list") or {}).get("lists", [])
    lst = next((x for x in lists if x["name"] == LIST_NAME), None)
    if lst:
        print(f"Reusing existing list {lst['id']} (delete it first if you want a clean re-run).")
    else:
        lst = _req(f"/space/{space['id']}/list", {"name": LIST_NAME}, "POST")
    list_id = lst["id"]
    print(f"List: https://app.clickup.com/{team['id']}/v/li/{list_id}\n")

    csv_path = Path(__file__).with_name("clickup_tasks.csv")
    created = 0
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            ws = (row.get("Workstream") or "").strip()
            desc = (
                f"{row.get('Description','').strip()}\n\n"
                f"Workstream: {ws} | Estimate: {row.get('Estimate (days)','')}d "
                f"| Depends on: {row.get('Depends On','') or 'none'}"
            )
            body = {"name": row["Task Name"].strip(), "description": desc}
            if ws:
                body["tags"] = [ws]
            email = NAME2EMAIL.get((row.get("Assignee") or "").strip())
            if email and email.lower() in members:
                body["assignees"] = [members[email.lower()]]
            if row.get("Priority", "").strip() in PRIORITY:
                body["priority"] = PRIORITY[row["Priority"].strip()]
            dm = due_ms(row.get("Due Date", ""))
            if dm:
                body["due_date"] = dm
                body["due_date_time"] = False
            r = _req(f"/list/{list_id}/task", body, "POST")
            status = r["id"] if r else "FAILED"
            created += 1 if r else 0
            print(f"  + {row['Task Name']:55.55}  {status}")
    print(f"\nCreated {created} tasks in list {list_id}.")


if __name__ == "__main__":
    main()
