"""The quarantine is a structural claim, so it gets a test rather than a habit."""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_pipeline_never_reaches_into_the_hidden_tree():
    offenders = []
    for path in (ROOT / "pipeline").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text()
        if "secret" in text.lower():
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"pipeline/ references the hidden tree: {offenders}"


def test_leakguard_is_clean():
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "leakguard.py")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout


def _probe_term():
    """Borrow a term from the hidden wordlist rather than hardcoding one here —
    a literal in this file would itself be a leak, and the guard would say so."""
    lines = (ROOT / "secret" / "forbidden_vocab.txt").read_text().splitlines()
    start = lines.index("[hard]")
    for line in lines[start + 1 :]:
        term = line.strip()
        if term and not term.startswith(("#", "[")):
            return term
    raise AssertionError("hidden wordlist has no hard-tier terms")


def _candidate_probe_term():
    """A term from the candidate domain's own section of the wordlist.

    Guarding a new domain is not the same as guarding the old one. A section
    can be added and be empty, or contain only terms that were pruned for
    colliding with pipeline vocabulary, and the tree would still look clean
    because nothing from that domain is in it yet. This finds a term the
    candidate section actually contributes, so the check below proves the guard
    would fire on the new domain rather than merely on the old one.
    """
    lines = (ROOT / "secret" / "forbidden_vocab.txt").read_text().splitlines()
    start = next(
        (i for i, line in enumerate(lines) if "candidate control domain" in line), None
    )
    assert start is not None, "the wordlist has no candidate-domain section"
    seen_header = False
    for line in lines[start:]:
        s = line.strip()
        if s.startswith("["):
            seen_header = True
            continue
        if seen_header and s and not s.startswith("#"):
            return s
    raise AssertionError("the candidate-domain section contributes no terms")


def test_guard_covers_the_candidate_domain_not_only_the_incumbent():
    planted = ROOT / "generated" / "_candidate_domain_probe.lean"
    planted.write_text(f"-- {_candidate_probe_term()}\n")
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "leakguard.py")],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 1, (
            "a term from the candidate domain passed the guard; its vocabulary is "
            "not actually covered"
        )
    finally:
        planted.unlink()


def test_leakguard_actually_catches_a_planted_violation():
    planted = ROOT / "generated" / "_quarantine_probe.lean"
    planted.write_text(f"-- {_probe_term()}\n")
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "leakguard.py")],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 1, "guard failed to notice a planted violation"
    finally:
        planted.unlink()


def test_guard_refuses_to_report_clean_on_a_tree_it_did_not_scan():
    """The failure this pins down was silent and total.

    `walk()` used to return quietly when a declared public root was missing, so
    moving the theory to a new directory would have produced `leakguard: clean`,
    exit 0, and three green tests — with a hard-tier term sitting in the theory
    source. A guard that reports clean on a directory it never opened is worse
    than no guard, because it is believed.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("lg", ROOT / "tools" / "leakguard.py")
    lg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lg)

    required = [d for d in lg.PUBLIC_DIRS if d not in lg.OPTIONAL_DIRS]
    assert required, "no mandatory public root is declared"
    for d in required:
        assert (ROOT / d).exists(), f"declared public root {d!r} is missing"

    original = list(lg.PUBLIC_DIRS)
    lg.PUBLIC_DIRS.append("definitely-not-a-real-directory-name")
    try:
        lg.assert_roots()
        raise AssertionError("the guard accepted a missing mandatory root")
    except SystemExit:
        pass
    finally:
        lg.PUBLIC_DIRS[:] = original


def test_commit_messages_are_scanned():
    """A channel that had no coverage for eight sprints.

    Every other check walks the working tree. A commit message is not in the
    working tree, so nothing looked at it — and unlike a file, a pushed message
    cannot be fixed by editing it. Scanning the history against the wordlist
    turned up a real hard-tier term in two messages.

    Only the hard tier applies: messages are prose, and the artifact tier exists
    because ordinary English words are unremarkable in prose.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("lg", ROOT / "tools" / "leakguard.py")
    lg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lg)

    assert hasattr(lg, "scan_commit_messages"), "commit messages are unscanned again"

    # a term nothing in this repository's history would legitimately contain
    planted = lg.scan_commit_messages(["zzzsentinelterm"])
    assert planted == [], "the sentinel matched something, so the scan is not selective"

    # and the real wordlist must come back clean over the amendable range
    hard, _ = lg.load_vocab()
    assert lg.scan_commit_messages(hard) == [], (
        "a hard-tier term is present in a commit message that has not been pushed "
        "yet, so it can still be amended — do that before pushing"
    )


def test_repository_root_files_are_scanned():
    """A file dropped at the root — a handoff note, a scratch plan — used to sit
    entirely outside the guard."""
    planted = ROOT / "_root_scan_probe.md"
    planted.write_text(f"{_probe_term()}\n")
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "leakguard.py")],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 1, "a forbidden term at the repository root passed the guard"
    finally:
        planted.unlink()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
