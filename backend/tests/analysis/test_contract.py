"""Smoke contract; integration tests with dedicated PostgreSQL still required."""
from app.modules.analysis.models import ACTIVE, TERMINAL

def test_state_sets_disjoint():
    assert not set(ACTIVE).intersection(TERMINAL)

def test_cancel_requested_is_active():
    assert 'cancel_requested' in ACTIVE

def test_failed_is_terminal():
    assert 'failed' in TERMINAL
