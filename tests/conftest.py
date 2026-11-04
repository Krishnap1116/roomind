"""Test-only speed: judge debounce off, so live tests stay instant."""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import roomind as S
import roomind.remind as remind


@pytest.fixture(autouse=True)
def _fast_judge(monkeypatch):
    monkeypatch.setattr(S, "JUDGE_IDLE_S", 0.0)
    monkeypatch.setattr(S, "JUDGE_MAXWAIT_S", 0.0)


@pytest.fixture(autouse=True)
def _night_no_nudge(monkeypatch):
    """Pin the suite clock to 00:01: before any reminder time."""
    monkeypatch.setattr(remind, "now_local",
                        lambda: datetime.datetime(2026, 11, 3, 0, 1))
