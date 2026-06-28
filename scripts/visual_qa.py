#!/usr/bin/env python3
"""H8 visual-QA gate: render migrated Liveboard(s) to PNG and confirm they render to a
real, non-trivial image (the automated form of "open it and look"). Saves each PNG under
out/visual_qa/ for a human read against the Sisense source. Exits non-zero on any blank/errored render.

    PYTHONPATH=. .venv/bin/python scripts/visual_qa.py [<liveboard-guid> ...]
"""
import pathlib
import sys

import yaml

from sisense2ts.load import ts_client
from sisense2ts.verify import visual

DEFAULT = ["462c1712-c2fa-43cc-923d-f73270522ae6"]   # latest faithful auto-converted ECommerce (9/9 AUTO)


def main(guids):
    T = yaml.safe_load(open("config.yaml"))["thoughtspot"]
    tok = ts_client.get_token(T)
    out = pathlib.Path("out/visual_qa")
    out.mkdir(parents=True, exist_ok=True)
    rc = 0
    for g in guids:
        try:
            data = visual.render(T["base_url"], tok, g, "PNG")
        except Exception as e:
            print(f"  [RED  ] {g} -> render failed: {e}")
            rc = 1
            continue
        ok, why = visual.valid_image(data, "PNG")
        path = out / f"{g}.png"
        path.write_bytes(data)
        print(f"  [{'GREEN' if ok else 'RED  '}] {g} -> {path} ({why})")
        rc = rc or (0 if ok else 1)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or DEFAULT))
