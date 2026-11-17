"""interestkit on the exported audit corpora reproduces the audit exactly.

Each declaration in kit/data/euclean carries, under `reference`, the values the
pre-registered audit computed with euclean's own code. Recomputing them from
the library alone, and requiring agreement, is what makes the kit the audited
metric rather than a lookalike. These files are committed, so this runs in CI.
"""

import hashlib
import json
import math
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit"))

from interestkit import Library, metric  # noqa: E402

DATA = ROOT / "kit" / "data" / "euclean"
MANIFEST = json.loads((DATA / "MANIFEST.json").read_text()) if (DATA / "MANIFEST.json").exists() else {"corpora": []}
FILES = [DATA / c["file"] for c in MANIFEST["corpora"]]


def test_the_export_is_complete_and_unaltered():
    assert len(FILES) == 12
    for c in MANIFEST["corpora"]:
        data = (DATA / c["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == c["sha256"]


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_kit_reproduces_the_audit(path):
    lib = Library.load(path)
    thms = lib.theorems()
    assert len(thms) == next(c["statements"] for c in MANIFEST["corpora"] if c["file"] == path.name)
    users = lib.direct_users()
    V = {(c, m): metric.proof_cost(lib, c, m) for c in ("loc", "term", "tac") for m in ("dag", "tree")}
    for d in thms:
        ref, n = d["reference"], d["name"]
        assert users[n] == ref["direct_users"], n
        L = {s: metric.description_length(lib, d, (), metric.SIZES[s]) for s in ("raw", "canon")}
        assert L["raw"] == ref["L0_raw"] and L["canon"] == ref["L0_canon"], n
        for (c, m), v in V.items():
            assert v[n] == int(ref[f"V_{c}_{m}"]), (n, c, m)
            for s in ("raw", "canon"):
                got = metric.log10(metric.interestingness(v[n], L[s]))
                assert math.isclose(got, ref[f"log10_I0_{c}_{m}_{s}"], rel_tol=1e-12, abs_tol=1e-12), (n, c, m, s)
