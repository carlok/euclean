"""interestkit: an open, tested implementation of the interestingness quantities
of Patel et al., *Learning to Discover Interesting Mathematics*
(arXiv:2609.28603), over a plain JSON library format, plus checks for any
scoring rule against ground truth.

Not affiliated with or endorsed by the paper's authors. Every choice the paper
leaves open is a parameter here, named where it is made.
"""

from . import evaluate, filters, loop, metric
from .library import Library

__all__ = ["Library", "metric", "filters", "loop", "evaluate"]
