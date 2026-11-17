"""The guard's matching engine, its scanned roots and its output.

These use synthetic terms, never the wordlist, so they run without secret/
and in CI. The guard's behaviour on the real wordlist is covered by
test_quarantine.py, which needs secret/.
"""

import importlib.util
import pathlib
import random
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("leakguard", ROOT / "tools" / "leakguard.py")
lg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lg)

# Prefixes of one another, multi-word and hyphenated phrases: the cases where a
# prefix tree and a flat alternation could disagree.
TERMS = ["al", "alpha", "alphabet", "beta", "beta gamma", "gamma", "delta-x", "wire", "wires"]


def _flat(terms):
    """The guard's matcher before the prefix tree, kept here as the reference."""
    return re.compile(r"(?<![a-z0-9])(" + "|".join(terms) + r")\w*", re.IGNORECASE)


def _reference_hits(text, terms):
    rx = _flat(terms)
    out = {}
    for i, row in enumerate(text.splitlines(), 1):
        m = rx.search(row)
        if m:
            out[i] = m.start()
    return out


def _engine_hits(text, terms):
    data = text.encode("utf-8")
    hits = lg.scan_bytes(data, [("t", lg._term_re_bytes(terms))])
    rows = text.splitlines()
    out = {}
    for _, i, term, _ in hits:
        out[i] = rows[i - 1].lower().find(term.lower())
    return out


def _random_text(seed, n=6000):
    rnd = random.Random(seed)
    pieces = []
    for _ in range(n):
        w = rnd.choice(TERMS)
        r = rnd.random()
        w = w if r < .3 else "x" + w if r < .45 else w + "zz" if r < .6 else "_" + w if r < .75 else w.upper()
        pieces += [w, rnd.choice([" ", "_", ".", "-", "", "é", "∀", "\n", "\n"])]
    return "".join(pieces)


def test_prefix_tree_flags_the_same_rows_as_the_flat_alternation():
    for seed in range(5):
        text = _random_text(seed)
        assert set(_reference_hits(text, TERMS)) == set(_engine_hits(text, TERMS))


def test_first_hit_per_row_starts_at_the_same_column():
    text = _random_text(11)
    ref = _reference_hits(text, TERMS)
    rows = text.splitlines()
    for i, col in ref.items():
        m = lg._term_re(TERMS).search(rows[i - 1])
        assert m and m.start() == col


def test_identifier_boundary_is_unchanged():
    rx = lg._term_re(["wire"])
    assert rx.search("rewire") is None            # preceded by a letter
    assert rx.search("rewire2") is None
    assert rx.search("_wire") is not None         # underscore is a boundary
    assert rx.search("is_wire") is not None
    assert rx.search("Wires") is not None         # case-insensitive, suffix allowed
    assert rx.search("2wire") is None             # preceded by a digit


def test_one_huge_row_is_scanned_in_one_pass_and_reports_one_hit():
    data = b'{"x": "' + b"a" * 5_000_000 + b' wire "}'
    hits = lg.scan_bytes(data, [("t", lg._term_re_bytes(["wire"]))])
    assert [(h[1], h[2]) for h in hits] == [(1, "wire")]
    assert len(hits[0][3]) <= 90                  # context is a window, not the row


def test_row_numbers_count_newlines():
    data = b"one\ntwo\nthree wire\nfour\nwire five\n"
    hits = lg.scan_bytes(data, [("t", lg._term_re_bytes(["wire"]))])
    assert [h[1] for h in hits] == [3, 5]


def test_non_utf8_files_are_still_skipped():
    assert lg._is_utf8("plain ascii and ∀".encode())
    assert not lg._is_utf8(b"\xff\xfe\x00binary")
    # a multi-byte character split across the chunk boundary is still valid
    assert lg._is_utf8("∀".encode() * 10, chunk=4)


def test_ci_configuration_is_a_scanned_root_on_the_hard_tier():
    assert ".github" in lg.PUBLIC_DIRS
    assert ".github" in lg.OPTIONAL_DIRS
    assert ".github" not in lg.ARTIFACT_DIRS
    if (ROOT / ".github").exists():
        assert any(p.suffix in (".yml", ".yaml") for p in lg.walk(".github"))


def test_default_report_hides_terms_and_context(capsys):
    hits = [("hard", "docs/x.md:3", "TERMVALUE", "some CONTEXTVALUE here")]
    lg.report(hits)
    out = capsys.readouterr().out
    assert "docs/x.md:3" in out
    assert "TERMVALUE" not in out and "CONTEXTVALUE" not in out
    lg.report(hits, show=True)
    out = capsys.readouterr().out
    assert "TERMVALUE" in out and "CONTEXTVALUE" in out
