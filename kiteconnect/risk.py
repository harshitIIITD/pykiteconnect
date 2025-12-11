# -*- coding: utf-8 -*-
"""
    risk.py

    Local pre-trade risk checks for Kite Connect REST flows.
"""
import logging
import threading

import kiteconnect.exceptions as ex

log = logging.getLogger(__name__)


class RiskEngine(object):
    """Simple in-process risk engine to guard outbound orders."""

    def __init__(self,
                 max_drawdown_pct=0.02,
                 max_quantity=None,
                 max_price_deviation=0.01,
                 ltp_fetcher=None):
        """
        Initialize risk engine.

        - `max_drawdown_pct` daily loss threshold (0.02 = 2%).
        - `max_quantity` maximum allowed absolute quantity per order.
        - `max_price_deviation` allowed deviation (fraction) from LTP for limit orders.
        - `ltp_fetcher` optional callable exchange, tradingsymbol -> float.
        """
        self.max_drawdown_pct = max_drawdown_pct
        self.max_quantity = max_quantity
        self.max_price_deviation = max_price_deviation
        self._ltp_fetcher = ltp_fetcher

        self._start_nav = None
        self._current_nav = None
        self._kill_switch = False
        self._lock = threading.Lock()

    def set_ltp_fetcher(self, fetcher):
        if fetcher and not callable(fetcher):
            raise TypeError("ltp_fetcher must be callable(exchange, tradingsymbol) -> price")
        self._ltp_fetcher = fetcher

    def update_nav(self, nav):
        """Update current account NAV; sets start NAV if not present."""
        with self._lock:
            if self._start_nav is None:
                self._start_nav = nav
            self._current_nav = nav

    def reset_nav(self, nav=None):
        with self._lock:
            self._start_nav = nav
            self._current_nav = nav

    def engage_kill_switch(self):
        """Block new trades until reset."""
        with self._lock:
            self._kill_switch = True

    def release_kill_switch(self):
        with self._lock:
            self._kill_switch = False

    def is_kill_switch_engaged(self):
        with self._lock:
            return self._kill_switch

    def evaluate_order(self, params, force=False):
        """Validate order dict. Raises RiskException on failure."""
        if not params:
            return

        with self._lock:
            if self._kill_switch and not force:
                raise ex.RiskException("Kill switch engaged; blocking new orders")

            self._check_drawdown_locked()
            self._check_fat_finger_locked(params)

    def _check_drawdown_locked(self):
        if self._start_nav is None or self._current_nav is None:
            return

        if self._start_nav <= 0:
            return

        drawdown = (self._start_nav - self._current_nav) / float(self._start_nav)
        if drawdown >= self.max_drawdown_pct:
            self._kill_switch = True
            raise ex.RiskException("Max drawdown breached; kill switch engaged")

    def _check_fat_finger_locked(self, params):
        quantity = params.get("quantity")
        price = params.get("price")
        exchange = params.get("exchange")
        tradingsymbol = params.get("tradingsymbol")

        if self.max_quantity is not None and quantity is not None:
            if abs(int(quantity)) > int(self.max_quantity):
                raise ex.RiskException("Quantity exceeds configured fat-finger limit")

        # Only check price deviation for limit orders when fetcher is available and price is set.
        if price is None or not self._ltp_fetcher:
            return

        try:
            ltp = self._ltp_fetcher(exchange, tradingsymbol)
        except Exception as fetch_err:  # pragma: no cover - defensive
            log.warning("LTP fetch failed for %s:%s: %s", exchange, tradingsymbol, fetch_err)
            return

        if ltp:
            deviation = abs(float(price) - float(ltp)) / float(ltp)
            if deviation > self.max_price_deviation:
                raise ex.RiskException("Price deviates beyond allowed threshold from LTP")
