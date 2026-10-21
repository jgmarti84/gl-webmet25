"""In-memory stand-in for gl-tracker's ``pipeline.Salidas``.

gl-tracker writes its results to SpatiaLite. We never want that here: a request
would produce a ~7 MB database file of which only ~160 KB is payload (the rest
being SpatiaLite's EPSG catalogue), and nothing would ever read it back.

Swapping the sink is safe because ``pipeline.procesar()`` touches exactly two
things on its ``salidas`` argument::

    salidas.systems.output(list)            # pipeline.py:325
    salidas.forecasts[lead].output(list)    # pipeline.py:321

Nothing else. So an object with that shape is a complete substitute, and
``pipeline.Salidas`` — along with its ``cfg.out_dir.mkdir()`` and its SpatiaLite
connections — is simply never constructed. gl-tracker is not modified.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence


class Collector:
    """Accumulates whatever gl-tracker hands it."""

    __slots__ = ("rows",)

    def __init__(self) -> None:
        self.rows: List = []

    def output(self, systems: Iterable) -> None:
        self.rows.extend(systems)


class VolumeSink:
    """One volume's results.

    Built per volume rather than per job on purpose. A job-wide sink would
    force regrouping afterwards, and forecast systems carry
    ``timestamp = base + lead`` rather than the base observation time, so
    regrouping them means subtracting the lead back out. Per-volume keeps the
    association explicit and costs nothing.
    """

    def __init__(self, intervals: Sequence[int]) -> None:
        self.systems = Collector()
        self.forecasts = {int(t): Collector() for t in intervals}
