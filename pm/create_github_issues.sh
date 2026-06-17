#!/usr/bin/env bash
# Populate GitHub Issues + labels + a milestone from the build plan.
# Prereqs: `gh auth login` done, and run from inside the repo (after pushing it).
# Map the DEV_* vars to real GitHub usernames before running.
set -euo pipefail

DEV_A="${DEV_A:-}"   # e.g. export DEV_A=alice
DEV_B="${DEV_B:-}"
DEV_C="${DEV_C:-}"
LEAD="${LEAD:-}"
MILESTONE="Demo 2026-06-26"

assign() { [ -n "$1" ] && printf -- "--assignee %s" "$1" || printf ""; }

# labels (ignore errors if they already exist)
gh label create "ws:extract"  --color 1d76db 2>/dev/null || true
gh label create "ws:calc"     --color 5319e7 2>/dev/null || true
gh label create "ws:model"    --color 0e8a16 2>/dev/null || true
gh label create "ws:content"  --color fbca04 2>/dev/null || true
gh label create "ws:load"     --color d93f0b 2>/dev/null || true
gh label create "ws:infra"    --color b60205 2>/dev/null || true
gh label create "setup"       --color cccccc 2>/dev/null || true

# milestone
gh api "repos/{owner}/{repo}/milestones" -f title="$MILESTONE" -f due_on="2026-06-26T23:59:59Z" 2>/dev/null || true

mk() { # mk "title" "label" "assignee" "body"
  gh issue create --title "$1" --label "$2" --milestone "$MILESTONE" $(assign "$3") --body "$4"
}

mk "S1 Freeze IR contract (ir/models.py)" "setup" "$LEAD" "Sign off the frozen IR. Blocks B/C/D finalization."
mk "S2 Provision access (Sisense/Snowflake/TS)" "setup" "$LEAD" "Tokens + datamodel_id into config.yaml (gitignored)."
mk "A1 Sisense auth + pull one dashboard + datamodel" "ws:extract" "$DEV_A" "Verify REST endpoints against the trial. Dep: S2."
mk "A2 Save real trial exports into tests/fixtures" "ws:extract" "$DEV_A" "Replace synthetic fixtures. Dep: A1."
mk "A3 Implement parse_datamodel" "ws:extract" "$DEV_A" "raw -> SourceModel. Dep: A2."
mk "A4 Implement parse_dashboard + classify_filter" "ws:extract" "$DEV_A" "raw -> SourceDashboard."
mk "A5 Load Sisense data into Snowflake + TS Connection" "ws:infra" "$DEV_A" "RISK #1. Do early. Dep: S2."
mk "A6 TS import client + import trivial TML" "ws:load" "$DEV_A" "importMetadataTML. Dep: A5."
mk "A7 Wire end-to-end import in cli.py" "ws:load" "$DEV_A" "M2 dry-run. With Dev C. Dep: B4, C2."
mk "B1 translate_formula (supported subset)" "ws:calc" "$DEV_B" "LONG POLE. Flag UNSUPPORTED as MANUAL. Dep: S1."
mk "B2 Filter translation" "ws:calc" "$DEV_B" "member/range/relative/top-N/exclude."
mk "B3 model_to_tml: Table TML" "ws:model" "$DEV_B" "types + connection binding. Dep: S1."
mk "B4 model_to_tml: Model TML" "ws:model" "$DEV_B" "model_tables, joins+cardinality, column_ids. Dep: B3."
mk "B5 Calculated columns -> formulas" "ws:model" "$DEV_B" "uses B1 + coverage. Dep: B1, B4."
mk "B6 Unit tests + remove xfail" "ws:calc" "$DEV_B" "test_formula / test_model."
mk "C1 dashboard_to_tml: widget -> Answer" "ws:content" "$DEV_C" "CHART_TYPE_MAP + fields + measures. Dep: S1."
mk "C2 dashboard_to_tml: Liveboard TML" "ws:content" "$DEV_C" "visualizations + layout.tiles. Dep: C1."
mk "C3 Coverage report wiring + polish" "ws:content" "$DEV_C" "CoverageItems from all stages."
mk "C4 CLI end-to-end wiring + dry-run UX" "ws:load" "$DEV_C" "write TML + report to out/. Dep: A6, B4, C2."
mk "C5 QA end-to-end on real dashboard" "ws:content" "$DEV_C" "fix import errors via VALIDATE_ONLY. Dep: C4."
mk "C6 Demo script + known-limitations sheet" "ws:content" "$DEV_C" "for the Friday demo. Dep: M2."

echo "Done. Now create a Project board: gh project create --title 'sisense2ts sprint' (or via the web UI) and add these issues."
