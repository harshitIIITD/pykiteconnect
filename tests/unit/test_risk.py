# -*- coding: utf-8 -*-
import pytest

from kiteconnect.risk import RiskEngine
import kiteconnect.exceptions as ex


def test_kill_switch_blocks():
    engine = RiskEngine()
    engine.engage_kill_switch()
    with pytest.raises(ex.RiskException):
        engine.evaluate_order({"quantity": 1, "price": 100, "exchange": "NSE", "tradingsymbol": "INFY"})


def test_fat_finger_limit():
    engine = RiskEngine(max_quantity=5)
    with pytest.raises(ex.RiskException):
        engine.evaluate_order({"quantity": 10, "price": 100, "exchange": "NSE", "tradingsymbol": "INFY"})


def test_drawdown_trips_kill_switch():
    engine = RiskEngine(max_drawdown_pct=0.02)
    engine.update_nav(100)
    engine.update_nav(97)  # 3% drawdown
    with pytest.raises(ex.RiskException):
        engine.evaluate_order({"quantity": 1, "price": 100, "exchange": "NSE", "tradingsymbol": "INFY"})
    assert engine.is_kill_switch_engaged() is True
