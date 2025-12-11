# -*- coding: utf-8 -*-
"""
    monitoring.py

    Lightweight latency tracking and export hooks.
"""
import logging
import time
from collections import deque

log = logging.getLogger(__name__)


class LatencyEvent(object):
    """Represents a latency datapoint."""

    __slots__ = ["stage", "event_id", "t1", "t2", "t3", "t4", "meta"]

    def __init__(self, stage, event_id=None, t1=None, t2=None, t3=None, t4=None, meta=None):
        self.stage = stage
        self.event_id = event_id
        self.t1 = t1
        self.t2 = t2
        self.t3 = t3
        self.t4 = t4
        self.meta = meta or {}

    @property
    def end_to_end_ms(self):
        if self.t1 is None or self.t4 is None:
            return None
        return (self.t4 - self.t1) * 1000.0

    def as_dict(self):
        return {
            "stage": self.stage,
            "event_id": self.event_id,
            "t1": self.t1,
            "t2": self.t2,
            "t3": self.t3,
            "t4": self.t4,
            "meta": self.meta,
            "end_to_end_ms": self.end_to_end_ms
        }


class LatencySink(object):
    """Interface for latency sinks."""

    def publish(self, event):  # pragma: no cover - interface
        raise NotImplementedError


class InMemoryLatencySink(LatencySink):
    """Stores recent latency events in memory for dashboards/tests."""

    def __init__(self, maxlen=1000):
        self._events = deque(maxlen=maxlen)

    def publish(self, event):
        self._events.append(event.as_dict())

    @property
    def events(self):
        return list(self._events)


class LoggingLatencySink(LatencySink):
    """Logs latency events for quick visibility."""

    def __init__(self, logger=None):
        self._log = logger or log

    def publish(self, event):
        self._log.info("Latency %s %s ms - meta=%s", event.stage, event.end_to_end_ms, event.meta)


class LatencyTracker(object):
    """Captures timestamps for T1-T4 and sends them to a sink."""

    def __init__(self, sink=None, alert_threshold_ms=50):
        self.sink = sink or InMemoryLatencySink()
        self.alert_threshold_ms = alert_threshold_ms
        self._latest_tick_times = {}

    def mark_tick(self, instrument_token, ts=None):
        self._latest_tick_times[instrument_token] = ts or time.time()

    def mark_signal(self, instrument_token, ts=None):
        t2 = ts or time.time()
        t1 = self._latest_tick_times.get(instrument_token)
        self._emit("T2", event_id=instrument_token, t1=t1, t2=t2, meta={"instrument_token": instrument_token})

    def mark_order_send(self, event_id=None, t1=None, t2=None, meta=None):
        t3 = time.time()
        self._emit("T3", event_id=event_id, t1=t1, t2=t2, t3=t3, meta=meta)
        return t3

    def mark_order_confirm(self, event_id=None, t1=None, t2=None, t3=None, meta=None):
        t4 = time.time()
        event = self._emit("T4", event_id=event_id, t1=t1, t2=t2, t3=t3, t4=t4, meta=meta)
        if event and event.end_to_end_ms is not None and event.end_to_end_ms > self.alert_threshold_ms:
            log.warning("Latency alert: %sms for %s", event.end_to_end_ms, event_id)
        return t4

    def _emit(self, stage, event_id=None, t1=None, t2=None, t3=None, t4=None, meta=None):
        event = LatencyEvent(stage=stage, event_id=event_id, t1=t1, t2=t2, t3=t3, t4=t4, meta=meta or {})
        try:
            self.sink.publish(event)
        except Exception as err:  # pragma: no cover - defensive
            log.warning("Failed to publish latency event: %s", err)
        return event
