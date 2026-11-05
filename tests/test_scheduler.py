from datetime import datetime, timezone

from backuphub import db, jobs, scheduler

TZ = "America/Sao_Paulo"  # UTC-3


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_daily():
    # 05/11/2026 (quinta) 10:00 local = 13:00 UTC → próximo 02:00 local de sexta = 05:00 UTC
    nxt = scheduler.next_run(list(range(7)), ["02:00"], utc(2026, 11, 5, 13, 0), TZ)
    assert nxt == utc(2026, 11, 6, 5, 0)


def test_same_day_later_slot():
    nxt = scheduler.next_run(list(range(7)), ["06:00", "18:00"], utc(2026, 11, 5, 13, 0), TZ)
    assert nxt == utc(2026, 11, 5, 21, 0)


def test_weekly_sunday():
    nxt = scheduler.next_run([6], ["01:00"], utc(2026, 11, 5, 13, 0), TZ)
    assert nxt == utc(2026, 11, 8, 4, 0)  # domingo 08/11 01:00 local


def test_twice_a_week():
    first = scheduler.next_run([1, 4], ["23:30"], utc(2026, 11, 5, 13, 0), TZ)  # sexta 06/11
    second = scheduler.next_run([1, 4], ["23:30"], first, TZ)                    # terça 10/11
    assert first == utc(2026, 11, 7, 2, 30)
    assert second == utc(2026, 11, 11, 2, 30)


def test_empty_schedule():
    assert scheduler.next_run([], ["02:00"], utc(2026, 1, 1)) is None


def test_tick_fires_once(app, monkeypatch):
    calls = []
    monkeypatch.setattr(jobs, "enqueue_backup", lambda ids, policy=None, trigger="": calls.append((ids, trigger)))
    mid = db.insert("machines", {"name": "m1", "platform": "linux", "provider": "onprem", "created_at": db.utcnow()})
    pid = db.insert("policies", {"name": "p", "days": list(range(7)), "times": ["02:00"], "machine_ids": [mid],
                                 "destination_id": None, "next_run_at": "2026-11-05T05:00:00+00:00",
                                 "created_at": db.utcnow()})
    now = utc(2026, 11, 5, 5, 0, 30)
    assert scheduler.tick(now) == [pid]
    assert scheduler.tick(now) == []  # já reservado: não duplica
    assert calls == [([mid], "schedule")]
    assert db.get("policies", pid)["next_run_at"] > now.isoformat()
