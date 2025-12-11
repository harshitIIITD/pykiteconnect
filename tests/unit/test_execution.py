# -*- coding: utf-8 -*-
import pytest

from kiteconnect.execution import SmartExecution
from kiteconnect.connect import KiteConnect


class DummyKC(object):
    VARIETY_ICEBERG = "iceberg"
    ORDER_TYPE_LIMIT = "LIMIT"
    TRANSACTION_TYPE_BUY = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"
    PRODUCT_CNC = "CNC"

    def __init__(self, ltp_value=100):
        self.calls = []
        self.cancelled = []
        self.ltp_value = ltp_value

    def place_order(self, **kwargs):
        self.calls.append(kwargs)
        return "id-%s" % (len(self.calls) - 1)

    def cancel_order(self, variety, order_id):
        self.cancelled.append((variety, order_id))

    def ltp(self, token):
        return {token: {"last_price": self.ltp_value}}


def test_place_iceberg_slices_and_passes_flags():
    kc = DummyKC()
    execu = SmartExecution(kc)

    order_ids = execu.place_iceberg(
        exchange="NSE",
        tradingsymbol="INFY",
        transaction_type=kc.TRANSACTION_TYPE_BUY,
        quantity=250,
        product=kc.PRODUCT_CNC,
        order_type=kc.ORDER_TYPE_LIMIT,
        price=100,
        iceberg_size=100,
    )

    assert len(order_ids) == 3
    assert all(call["variety"] == kc.VARIETY_ICEBERG for call in kc.calls)
    assert kc.calls[0]["iceberg_legs"] == 3
    assert kc.calls[0]["iceberg_quantity"] == 84  # ceil(250/3)


def test_smart_chase_reprices_when_market_moves():
    kc = DummyKC(ltp_value=110)
    execu = SmartExecution(kc)

    final_id = execu.smart_chase_limit(
        variety="regular",
        exchange="NSE",
        tradingsymbol="INFY",
        transaction_type=kc.TRANSACTION_TYPE_BUY,
        quantity=1,
        product=kc.PRODUCT_CNC,
        limit_price=100,
        ltp=100,
        tick_size=0.05,
        chase_pct=0.001,
        max_reprices=1,
        wait_seconds=0,
    )

    # First order cancelled and replaced with improved price
    assert kc.cancelled[0][1] == "id-0"
    assert final_id == "id-1"
    assert kc.calls[-1]["price"] > 100


def test_place_order_with_gtt_stop_uses_entry_price():
    kc = KiteConnect(api_key="k", access_token="t")

    recorded = {}

    def fake_place_order(**kwargs):
        recorded["order"] = kwargs
        return "order-1"

    def fake_place_gtt(*args, **kwargs):
        recorded["gtt"] = {"args": args, "kwargs": kwargs}
        return {"trigger_id": 321}

    kc.place_order = fake_place_order
    kc.place_gtt = fake_place_gtt
    kc._ltp_from_api = lambda exchange, tradingsymbol: 200

    res = kc.place_order_with_gtt_stop(
        variety="regular",
        exchange="NSE",
        tradingsymbol="INFY",
        transaction_type=kc.TRANSACTION_TYPE_BUY,
        quantity=2,
        product=kc.PRODUCT_CNC,
        order_type=kc.ORDER_TYPE_LIMIT,
        entry_price=210,
        stop_loss_percentage=0.02,
    )

    assert res["order_id"] == "order-1"
    assert res["gtt"]["trigger_id"] == 321
    assert recorded["gtt"]["kwargs"]["trigger_values"] == [pytest.approx(205.8, rel=1e-6)]
    assert recorded["gtt"]["kwargs"]["orders"][0]["transaction_type"] == kc.TRANSACTION_TYPE_SELL
