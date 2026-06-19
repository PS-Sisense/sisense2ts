# Team workflow

How the three of us work in this repo without stepping on each other. Read it once; the
cheat sheet at the bottom is your day-to-day. Tasks live in ClickUp; this is the "how we
commit code" guide.

## How syncing works (the mental model)

- When you `git clone`, you get your **own full local copy** of the code and its history.
- It is **not** live-synced like a Google Doc. GitHub (`PS-Sisense/sisense2ts`) is the shared hub.
- You move changes through GitHub deliberately:
  - `git push` sends **your** commits **up** to GitHub.
  - `git pull` brings **everyone else's** commits **down** into your copy.
- So the loop is always: **pull -> work -> commit -> pull -> push.**

## Who owns what

We each own different files, so merges are almost always automatic.

| Person | Lane | Files | ClickUp tasks |
|---|---|---|---|
| Anuj (Dev A) | Pipes & infra | `extract/`, `load/`, Snowflake + ThoughtSpot connection | S1-S4, A1-A7 |
| Pooja (Dev B) | Semantic | `sisense2ts/map/formula.py`, `sisense2ts/map/model.py` | B1-B6 |
| Apratim (Dev C) | Content & delivery | `sisense2ts/map/content.py`, `cli.py`, `report/`, `tests/` | C1-C6 |

## The one rule that prevents chaos

**Do not edit `sisense2ts/ir/models.py` (the frozen IR contract) without telling the team.**
Everyone's code is written against it. A silent change there breaks all three lanes at once.
If you think it needs a change, raise it first.

## One-time setup

```bash
git clone https://github.com/PS-Sisense/sisense2ts.git
cd sisense2ts
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                # should be green (some xfail is expected until the calc work lands)
```

Then open the folder in **Claude Code** (use "Add folder", or just launch Claude Code from
inside `sisense2ts`). Claude Code works on these local files directly. There is no GitHub
"connector" to set up, the clone is all you need.

## Daily loop

```bash
git pull                                  # 1. get everyone's latest
git checkout -b b1-formula                # 2. branch named after your task
# ... edit, then ...
git add -A
git commit -m "B1: translate sum/count formulas"   # 3. commit small and often
git pull --rebase origin main             # 4. fold in others' changes before pushing
git push -u origin b1-formula             # 5. publish your branch
```
Then open a Pull Request on GitHub, get a quick look from one teammate, and merge to `main`.
Everyone else runs `git pull` to pick it up.

Prefer to work straight on `main`? It still works because our files rarely overlap, just run
`git pull --rebase` before every push. Branches are cleaner though, and let us review.

## Conventions

- Start each commit message with the task id: `B1: ...`, `C3: ...`, `A5: ...`.
- One task per PR. Small PRs merge fast.
- Keep `pytest` green before you merge.
- Never commit secrets. `config.yaml`, `*.token`, and `.env` are gitignored; keep real
  credentials there, not in tracked files.

## If you hit a merge conflict

Git marks the spots in the file with `<<<<<<<`, `=======`, `>>>>>>>`. Open the file, keep the
correct lines, delete the markers, then:
```bash
git add <file>
git rebase --continue   # or: git commit, if you were merging
```
Small, frequent pulls make this rare. Ask in the channel if a conflict looks scary.

## Working with ClickUp (and letting Claude update it)

Tasks live in ClickUp. Keep the board honest by letting your Claude update it as you go,
instead of manual bookkeeping.

Setup (once): generate **your own** ClickUp API token (ClickUp -> Settings -> Apps ->
API Token) and export it. Do not commit it.
```bash
export CLICKUP_TOKEN=pk_xxx_your_own_token
```
Get a task id from its ClickUp URL (last path segment) or the task's "Copy ID". Then:
```bash
python pm/clickup_task.py get      <task_id>                 # read the task
python pm/clickup_task.py comment  <task_id> "branch b1-formula up; sum/count translating; tests green"
python pm/clickup_task.py statuses <task_id>                 # valid status names
python pm/clickup_task.py status   <task_id> "in progress"
```

**The loop we want, per task:**
1. In your clone, open Claude Code.
2. Point it at the task and its spec: *"Implement B1. The spec is the docstring and TODOs
   in `sisense2ts/map/formula.py`; make `tests/test_formula.py` pass. Stay within the IR in
   `sisense2ts/ir/models.py`. Do not edit other lanes' files."*
3. When tests are green, have Claude commit, push your branch, then post a ClickUp comment
   and flip status with `pm/clickup_task.py`.

The detailed "how" for each task lives in the **stub docstrings and tests in the repo**, not
in the short ClickUp blurb. Point Claude at the file and the test and it has what it needs.

## Evolving the IR (it is a stable contract, not frozen forever)

"Frozen" means no silent, casual edits to `sisense2ts/ir/models.py`, because all three lanes
depend on it. It does not mean it can never change. Three cases:

1. **Sisense has something the IR does not model:** first reach for the `raw` dict that every
   IR object carries. It holds the original JSON, so you can usually get what you need with
   no contract change at all.
2. **A new field (additive):** add it with a default (e.g. `role: Optional[ColumnRole] = None`).
   This does not break anyone's existing code. Announce it, commit, done. Safe anytime.
3. **A breaking change (rename / remove / retype a field):** the only one needing care.
   Whoever hits it proposes it, we agree quickly, and ONE commit changes the field and updates
   every consumer together, tests staying green, then everyone pulls.

Expect the IR to flex once we hit **real Sisense data**. That is why extraction (A1/A2) is
front-loaded to Day 1-2: pulling a real dashboard pressure-tests the IR against reality before
B and C have built much on it. Treat the first real export as a validation gate, if the shape
is wrong we amend the contract then, deliberately, while the cost is low. The fixtures are a
stand-in until then.

## Cheat sheet

| Goal | Command |
|---|---|
| Get latest | `git pull` |
| Start a task | `git checkout -b <task-name>` |
| Save work | `git add -A && git commit -m "B1: ..."` |
| Integrate before pushing | `git pull --rebase origin main` |
| Publish | `git push -u origin <task-name>` |
| See what changed | `git status` / `git diff` |
| Run tests | `pytest` |
