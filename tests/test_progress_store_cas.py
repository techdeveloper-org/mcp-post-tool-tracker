"""Cross-process regression test for the compare-and-swap progress store.

The unguarded (pre-migration) shape of ``increment_progress`` and
``track_tool_usage`` was a plain ``load()`` -> mutate -> ``save()`` cycle on
``AtomicJsonStore``. Under concurrent writers that loses updates: two
processes can both load the same version, both compute "old + delta", and
whichever ``save()`` lands second silently discards the first.

Both tools now route their state update through
``AtomicJsonStore.modify()``, which retries the whole read-modify-write
cycle against a freshly loaded version whenever it loses a compare-and-swap
race. Every assertion in this file exercises ``modify()`` at its *default*
``max_attempts`` -- no call site in this repo or in these tests overrides
it. An inflated attempt budget can hide a real defect in the retry backoff
itself (lock-step, unjittered retries can keep losing to the same
contender), so raising the budget to make a test pass would prove nothing
about what a real caller, using the default, actually gets.

This test launches real OS subprocesses rather than threads because the
defect is cross-process: MCP server invocations for a single Claude Code
session are independent process launches over stdio, not threads sharing
one interpreter, so a thread-only test would pass against an
implementation that used nothing stronger than a ``threading.Lock``.

Modeled on ``mcp-base/tests/test_persistence_cas.py``. Worker/process counts
mirror the scale the base library's own maintainer used to catch the
unjittered-backoff regression (8 processes x 25 operations = 200), so the
numbers here are directly comparable to that verification.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from base.persistence import AtomicJsonStore

# Scale for uncapped counters (track_tool_usage's tool_counts field has no
# ceiling). Matches the 8 x 25 = 200 scale the base library was verified
# against after the jittered-backoff fix.
WORKERS = 8
INCREMENTS = 25

# Scale for increment_progress's total_progress field, which is a business
# rule ceiling (min(100, ...)), not a CAS artifact. 96 stays under that
# ceiling at the same 8-way process contention so a lost update is still
# distinguishable from the cap, while remaining close to the validated
# scale above.
CAPPED_WORKERS = 8
CAPPED_INCREMENTS = 12


_INCREMENT_PROGRESS_WORKER = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, sys.argv[1])
    import server
    from base.persistence import AtomicJsonStore

    server._progress_store = AtomicJsonStore(sys.argv[2])

    for _ in range(int(sys.argv[3])):
        server.increment_progress(delta=1, reason="cas-load-test")
    """
)

_TRACK_TOOL_USAGE_WORKER = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, sys.argv[1])
    import server
    from base.persistence import AtomicJsonStore

    server._progress_store = AtomicJsonStore(sys.argv[2])

    # Neutralized rather than left pointed at the real ~/.claude session:
    # track_tool_usage's own session lookup is unrelated to the store under
    # test, and leaving it live would both write tool-tracker.jsonl entries
    # into the developer's real session log as a side effect of running
    # this test, and make the flow-trace-derived complexity value (and
    # therefore the delta this test asserts on) depend on whatever real
    # session happens to be active on the machine running the suite.
    server._get_session_id = lambda: ""

    for _ in range(int(sys.argv[3])):
        server.track_tool_usage(tool_name="Read", tool_input="{}", is_error=False)
    """
)

_UNGUARDED_WORKER = textwrap.dedent(
    """
    import sys, time
    sys.path.insert(0, sys.argv[1])
    from base.persistence import AtomicJsonStore

    store = AtomicJsonStore(sys.argv[2])
    for _ in range(int(sys.argv[3])):
        data = store.load(default={"count": 0})
        data["count"] = data.get("count", 0) + 1
        time.sleep(0.001)
        try:
            store.save(data)
        except OSError:
            pass
    """
)


def _run_workers(script, repo_root, target, workers, increments):
    """Launch ``workers`` real subprocesses running ``script`` and return the
    final persisted state.

    Each subprocess independently imports the server module, points its
    module-level progress store at ``target``, and performs ``increments``
    updates. Waiting for every process to exit before reading the file
    guarantees the read observes the fully-settled result of all writers.

    Args:
        script: Python source executed via ``python -c`` in each subprocess.
        repo_root: Directory added to ``sys.path`` so ``server`` and
            ``base.persistence`` import inside the subprocess.
        target: Path to the shared JSON state file under test.
        workers: Number of concurrent subprocesses to launch.
        increments: Number of update calls performed by each subprocess.

    Returns:
        The parsed JSON contents of ``target`` after all subprocesses exit.
    """
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(repo_root), str(target), str(increments)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(workers)
    ]
    for proc in procs:
        proc.wait(timeout=180)
    return json.loads(Path(target).read_text(encoding="utf-8"))


class TestCrossProcessConcurrency:
    """The regression this whole CAS migration exists to prevent.

    Every ``modify()`` call below runs at the library default
    ``max_attempts`` -- none of these tests, and no call site in
    ``server.py``, overrides it.
    """

    def test_unguarded_cycle_loses_updates(self, tmp_path):
        """Control: proves this workload has enough contention to detect a
        lost update at all. If this assertion fails, the guarded tests below
        prove nothing -- they would be passing merely because the race was
        never actually exercised.
        """
        repo_root = Path(__file__).resolve().parent.parent
        target = tmp_path / "session-progress.json"
        target.write_text('{"count": 0}', encoding="utf-8")

        final = _run_workers(_UNGUARDED_WORKER, repo_root, target, WORKERS, INCREMENTS)
        assert final["count"] < WORKERS * INCREMENTS, (
            "unguarded load/save did not lose an update under contention; "
            "the concurrency guarantee below is therefore untested"
        )

    def test_increment_progress_loses_no_updates_across_processes(self, tmp_path):
        """Every increment_progress call from every process must survive.

        Exercises the actual MCP tool function end to end (decorator, JSON
        response, and the modify()-based state update), not just the
        underlying AtomicJsonStore primitive that mcp-base already covers.
        Scaled to CAPPED_WORKERS/CAPPED_INCREMENTS so total_progress's own
        100-point ceiling never triggers and cannot be mistaken for a lost
        update.
        """
        repo_root = Path(__file__).resolve().parent.parent
        target = tmp_path / "session-progress.json"

        final = _run_workers(
            _INCREMENT_PROGRESS_WORKER, repo_root, target,
            CAPPED_WORKERS, CAPPED_INCREMENTS,
        )
        assert final["total_progress"] == CAPPED_WORKERS * CAPPED_INCREMENTS

        leftovers = [p.name for p in tmp_path.iterdir() if p.name != target.name]
        assert leftovers == [], "temp or claim files were left behind"

    def test_track_tool_usage_tool_counts_loses_no_updates_across_processes(self, tmp_path):
        """The highest call-frequency site: track_tool_usage's tool_counts
        bookkeeping must survive concurrent writers at the same 8x25=200
        scale the base library's jittered-backoff fix was verified against.

        tool_counts has no ceiling (unlike total_progress), so this is the
        cleanest exact invariant available at full scale: final count must
        equal workers x increments, with no cap to obscure a loss.
        """
        repo_root = Path(__file__).resolve().parent.parent
        target = tmp_path / "session-progress.json"

        final = _run_workers(
            _TRACK_TOOL_USAGE_WORKER, repo_root, target, WORKERS, INCREMENTS
        )
        assert final["tool_counts"]["Read"] == WORKERS * INCREMENTS

        leftovers = [p.name for p in tmp_path.iterdir() if p.name != target.name]
        assert leftovers == [], "temp or claim files were left behind"
