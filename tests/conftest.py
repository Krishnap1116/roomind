"""Test-only speed: judge debounce off, so live tests stay instant."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import roomind as S


@pytest.fixture(autouse=True)
def _fast_judge(monkeypatch):
    monkeypatch.setattr(S, "JUDGE_IDLE_S", 0.0)
    monkeypatch.setattr(S, "JUDGE_MAXWAIT_S", 0.0)
