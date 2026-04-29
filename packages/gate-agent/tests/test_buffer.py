from __future__ import annotations

from pathlib import Path

import pytest

from gate_agent.buffer import EventBuffer
from gate_agent.events import GateEvent


def make_event(epoch: int = 1, direction: str = "in") -> GateEvent:
    return GateEvent.new(gate_id="gate-test", direction=direction, epoch=epoch, source="test")


@pytest.fixture
def buf(tmp_path: Path) -> EventBuffer:
    return EventBuffer(tmp_path / "buf.db")


def test_append_and_unsent_count(buf: EventBuffer) -> None:
    e1, e2 = make_event(), make_event()
    buf.append(e1, created_at_ms=1)
    buf.append(e2, created_at_ms=2)
    assert buf.unsent_count() == 2


def test_append_is_idempotent_on_event_id(buf: EventBuffer) -> None:
    e = make_event()
    buf.append(e, created_at_ms=1)
    buf.append(e, created_at_ms=2)  # same event_id; should be ignored
    assert buf.unsent_count() == 1


def test_fetch_unsent_orders_by_creation_time(buf: EventBuffer) -> None:
    e1 = make_event()
    e2 = make_event()
    buf.append(e2, created_at_ms=200)
    buf.append(e1, created_at_ms=100)
    rows = buf.fetch_unsent(limit=10)
    assert [r[0] for r in rows] == [e1.event_id, e2.event_id]


def test_mark_sent_makes_them_invisible(buf: EventBuffer) -> None:
    e = make_event()
    buf.append(e, created_at_ms=1)
    buf.mark_sent([e.event_id])
    assert buf.unsent_count() == 0


def test_flush_below_epoch_drops_only_old(buf: EventBuffer) -> None:
    old = make_event(epoch=1)
    new = make_event(epoch=2)
    buf.append(old, created_at_ms=1)
    buf.append(new, created_at_ms=2)
    flushed = buf.flush_below_epoch(2)
    assert flushed == 1
    rows = buf.fetch_unsent(limit=10)
    assert len(rows) == 1
    assert rows[0][0] == new.event_id


def test_increment_attempt(buf: EventBuffer) -> None:
    e = make_event()
    buf.append(e, created_at_ms=1)
    buf.increment_attempt(e.event_id)
    buf.increment_attempt(e.event_id)
    rows = buf.fetch_unsent(limit=10)
    assert rows[0][2] == 2


def test_purge_sent_older_than(buf: EventBuffer) -> None:
    e = make_event()
    buf.append(e, created_at_ms=0)
    buf.mark_sent([e.event_id])
    purged = buf.purge_sent_older_than(ms_age=1000, now_ms=10_000)
    assert purged == 1
