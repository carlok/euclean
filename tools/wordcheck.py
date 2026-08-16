"""Check a piece of prose against the wordlist before it is written down.

`leakguard` scans the whole tree and takes minutes. That is right for a gate and
wrong for a habit: the cost lands after the prose exists, which is how this
repository has repeatedly committed a listed term while describing the guard
that catches listed terms.

This reads text on stdin and reports hits in under a second, so the check can
come before the writing.

    echo "some sentence" | python3 tools/wordcheck.py
    python3 tools/wordcheck.py < draft.md

Exit code 0 clean, 1 on any hit. Needs `secret/`, like the guard, and reports
that rather than reporting clean.
"""

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("lg", ROOT / "tools" / "leakguard.py")
lg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lg)


def main():
    hard, artifacts = lg.load_vocab()
    text = sys.stdin.read()
    hits = []
    for tier, terms in (("hard", hard), ("artifact", artifacts)):
        pat = lg._term_re(terms)
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in pat.finditer(line):
                hits.append((tier, lineno, m.group(0), line.strip()[:80]))

    if not hits:
        print("wordcheck: clean")
        return 0
    print(f"wordcheck: {len(hits)} hit(s)\n")
    for tier, lineno, term, line in hits:
        print(f"  [{tier}] line {lineno}  ({term})")
        print(f"          {line}")
    print("\nThe artifact tier applies only inside generated trees and prose;")
    print("the hard tier applies everywhere. Rename rather than relax.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
