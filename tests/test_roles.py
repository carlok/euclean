"""Gate for proof-role concept mining.

The interesting assertion here is the first one. `applications` used to walk a
modus-ponens spine as if the spine were an ordinary child, so a rule applied to
three premises was reported three times — as `f a`, `f a b`, and `f a b c` —
under three different motif keys, all describing one inference. Motif counts and
the number of distinct motifs were both inflated by it, and nothing downstream
could have noticed, because every count was wrong in the same direction.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.concepts import roles  # noqa: E402
from pipeline.kernel import formula as F, proof as P, theory  # noqa: E402
from pipeline.patterns import motifs  # noqa: E402

T = theory.load()
C = F.Const

# a rule with exactly two premises and an atomic conclusion
TWO_PREMISE = next(
    n
    for n in T.axiom_names
    if T.statement(n)["kind"] == "forall"
    and len(F.premises(T.statement(n)["body"])[0]) == 2
    and F.premises(T.statement(n)["body"])[1]["kind"] == "atom"
)


def test_applications_reports_each_application_once():
    a, b = C("ca"), C("cb")
    args = [a, b, b, a, b, a]
    inst = F.instantiate(T.statement(TWO_PREMISE), args)
    premises, _ = F.premises(inst)

    pf = P.Ax(TWO_PREMISE, args)
    for i, prem in enumerate(premises):
        pf = P.MP(pf, P.Hyp(f"h{i}"))

    apps = motifs.applications(pf)
    assert len(apps) == 1, f"a single application was reported {len(apps)} times: {apps}"
    rule, arg_heads = apps[0]
    assert rule == TWO_PREMISE
    assert len(arg_heads) == 2, f"expected both premises in one motif, got {arg_heads}"


def test_rule_fed_rejects_all_hypothesis_motifs():
    assert not roles.rule_fed(("a0", ("<hyp>", "<hyp>")))
    assert roles.rule_fed(("a0", ("<hyp>", "t0_00009")))


def _corpus():
    path = pathlib.Path(__file__).resolve().parents[1] / "runs" / "main" / "corpus.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def test_candidates_are_composite_lemmas_the_kernel_accepts():
    records = _corpus()
    if not records:
        print("  (no corpus at runs/main; skipping)")
        return
    cands = roles.candidates(records, T, min_support=10, top=60)
    assert cands, "no role candidates mined from a corpus this size"
    for c in cands:
        assert c["source"] == "proof-role"
        assert c["statement_ast"] is not None and c["proof_ast"] is not None
        # every candidate must genuinely consume another rule's output
        assert any(not a.startswith("<") for a in c["motif"]["arguments"])
    failures = roles.verify(records, cands)
    assert not failures, f"{len(failures)} batch(es) of role lemmas rejected by the kernel"


def test_candidates_exclude_restatements_and_weakenings():
    records = _corpus()
    if not records:
        print("  (no corpus at runs/main; skipping)")
        return
    from pipeline.canon import normalize as N

    known = {N.key(s) for s in T.env.values()}
    known |= {N.key(r["statement_ast"]) for r in records}
    for c in roles.candidates(records, T, min_support=10, top=60):
        assert N.key(c["statement_ast"]) not in known, "a known theorem came back as a candidate"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
