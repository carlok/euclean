"""Gate for the quantified concept language.

One test here matters more than the rest. A rule whose premise is an existential
can never fire: `chainer/matching.py` files facts under `('atom', rel)` and an
existential premise looks in `('exists',)`, which nothing is ever filed under.
The rule sits in the environment, matches nothing, contributes nothing, and
reports nothing — the failure that killed the rejected control's identity axiom,
found only after a sprint had been spent on it.

`test_bridges_are_live` is the check that it has not happened again.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.chainer import matching as M  # noqa: E402
from pipeline.concepts import quantified as Q  # noqa: E402
from pipeline.kernel import formula as F, theory, verify  # noqa: E402

T = theory.load()
ROOT = pathlib.Path(__file__).resolve().parents[1]


def _corpus():
    p = ROOT / "runs" / "main" / "corpus.json"
    return json.loads(p.read_text()) if p.exists() else None


def _top(n=6, support=6):
    records = _corpus()
    if not records:
        return None
    cands = sorted(Q.candidates(records, min_support=support), key=lambda c: -c["support"])[:n]
    for i, c in enumerate(cands):
        c["name"] = f"Q{i:02d}"
    return cands


def test_an_existential_premise_cannot_be_matched():
    """The fact that forces the whole bridge design. Pinned so it stays true."""
    ex = F.Exists(["z"], F.Atom("R0", [F.Var("x"), F.Var("y"), F.Var("z")]))
    fact = F.Atom("R0", [F.Const("p0"), F.Const("p1"), F.Const("p2")])
    assert M.match_formula(ex, fact, {}) is None
    assert M.index_key(ex) != M.index_key(fact), (
        "an existential premise and an atomic fact now share a bucket; if matching "
        "gained an exists case, the curried introduction bridge may be unnecessary"
    )


def test_candidates_are_genuinely_quantified():
    cands = _top()
    if not cands:
        print("  (no corpus; skipping)")
        return
    assert cands, "no quantified candidates mined from a corpus this size"
    for c in cands:
        assert c["body"]["kind"] == "exists"
        assert c["witness"] not in c["params"], "the witness leaked into the parameters"
        assert c["source"] == "quantified"


def test_bridges_are_live():
    """No bridge may be inert. This is the whole point of currying the intro."""
    cands = _top()
    if not cands:
        print("  (no corpus; skipping)")
        return
    rows = Q.liveness(T, cands, seed=0)
    inert = [r["bridge"] for r in rows if r["inert"]]
    assert not inert, f"inert bridges, contributing nothing and saying nothing: {inert}"
    fired = [r for r in rows if r["derivations"] > 0]
    assert fired, "no bridge fired at all; the concepts cannot participate in search"


def test_lean_accepts_the_definitions_and_bridges():
    cands = _top()
    if not cands:
        print("  (no corpus; skipping)")
        return
    lines = ["import Theory.Anonymous", "set_option linter.unusedVariables false", ""]
    for c in cands:
        lines.append(Q.emit_definition(c["name"], c["body"], c["params"]))
        intro, elims = Q.emit_bridges(c["name"], c["body"], c["params"], c["witness"])
        lines.append(intro)
        lines.extend(elims)

    path = verify.THEORY_DIR / "Theory" / "Quantified.lean"
    path.write_text("\n".join(lines))
    verify.lean_env()
    _, ok, log = verify.check_file(path)
    assert ok, "\n".join(log.splitlines()[:12])


def test_introduction_premises_are_atomic():
    """Curried, so the engine can match them. Stated as an assertion, not a hope."""
    cands = _top()
    if not cands:
        print("  (no corpus; skipping)")
        return
    env, _ = Q.bridge_statements(cands)
    for name, stmt in env.items():
        if not name.endswith("_intro"):
            continue
        premises, _ = F.premises(stmt["body"])
        assert premises, f"{name} has no premises to match on"
        for p in premises:
            core = p["arg"] if p["kind"] == "not" else p
            assert core["kind"] in ("atom", "eq"), (
                f"{name} has a non-atomic premise ({core['kind']}); the engine "
                "cannot match it and the bridge would be inert"
            )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
