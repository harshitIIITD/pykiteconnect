# -*- coding: utf-8 -*-
"""
    execution.py

    Smart execution helpers for slicing and chasing orders.
"""
import math
import time
import logging

import kiteconnect.exceptions as ex

log = logging.getLogger(__name__)


class SmartExecution(object):
    """Execution utilities built on top of KiteConnect."""

    def __init__(self, kc):
        self.kc = kc

    def place_iceberg(self, *, exchange, tradingsymbol, transaction_type, quantity, product,
                      order_type, price=None, validity=None, iceberg_size=100, tag=None):
        """
        Slice a large order into Iceberg legs.

        - `iceberg_size` max quantity per leg.
        """
        if iceberg_size <= 0:
            raise ex.InputException("iceberg_size must be positive")

        legs = int(math.ceil(float(quantity) / float(iceberg_size)))
        chunk_qty = int(math.ceil(float(quantity) / float(legs)))

        created = []
        remaining = int(quantity)
        for _ in range(legs):
            leg_qty = min(chunk_qty, remaining)
            params = {
                "variety": self.kc.VARIETY_ICEBERG,
                "exchange": exchange,
                "tradingsymbol": tradingsymbol,
                "transaction_type": transaction_type,
                "quantity": leg_qty,
                "product": product,
                "order_type": order_type,
                "price": price,
                "validity": validity,
                "iceberg_legs": legs,
                "iceberg_quantity": chunk_qty,
                "tag": tag
            }
            order_id = self.kc.place_order(**params)
            created.append(order_id)
            remaining -= leg_qty
        return created

    def smart_chase_limit(self, *, variety, exchange, tradingsymbol, transaction_type, quantity,
                          product, limit_price, ltp, tick_size=0.05, chase_pct=0.001,
                          validity=None, tag=None, max_reprices=2, wait_seconds=0.5):
        """
        Place a limit order and chase the price if it moves away.

        - `chase_pct` fraction of LTP to move price when re-submitting.
        - `max_reprices` number of times to cancel/replace.
        - `ltp` current last traded price used to seed and chase.
        """
        if ltp is None:
            raise ex.InputException("ltp is required for smart chasing")

        def _round_price(p):
            return round(float(p) / float(tick_size)) * float(tick_size)

        current_price = limit_price
        order_id = self.kc.place_order(
            variety=variety,
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=transaction_type,
            quantity=quantity,
            product=product,
            order_type=self.kc.ORDER_TYPE_LIMIT,
            price=current_price,
            validity=validity,
            tag=tag
        )

        # Decide side for chasing
        side = 1 if transaction_type == self.kc.TRANSACTION_TYPE_BUY else -1

        for _ in range(max_reprices):
            time.sleep(wait_seconds)
            latest_ltp = ltp
            try:
                quote_key = "%s:%s" % (exchange, tradingsymbol)
                latest_ltp = self.kc.ltp(quote_key)[quote_key]["last_price"]
            except Exception as fetch_err:  # pragma: no cover - best-effort
                log.debug("LTP fetch failed during chase: %s", fetch_err)

            # If order far from market, chase by small increment.
            desired_price = _round_price(latest_ltp + side * chase_pct * latest_ltp)
            # For buys we want price >= desired, for sells price <= desired.
            if (side == 1 and desired_price > current_price) or (side == -1 and desired_price < current_price):
                try:
                    self.kc.cancel_order(variety, order_id)
                except Exception as cancel_err:  # pragma: no cover - ignore cancel failure
                    log.debug("Cancel failed during chase: %s", cancel_err)
                current_price = desired_price
                order_id = self.kc.place_order(
                    variety=variety,
                    exchange=exchange,
                    tradingsymbol=tradingsymbol,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    product=product,
                    order_type=self.kc.ORDER_TYPE_LIMIT,
                    price=current_price,
                    validity=validity,
                    tag=tag
                )
        return order_id
