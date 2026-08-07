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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
