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
