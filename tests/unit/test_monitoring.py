# -*- coding: utf-8 -*-
import time

from kiteconnect.monitoring import LatencyTracker, InMemoryLatencySink


def test_latency_tracker_records_end_to_end():
    sink = InMemoryLatencySink()
    tracker = LatencyTracker(sink=sink, alert_threshold_ms=1_000)

    t1 = time.time()
    tracker.mark_tick(123, ts=t1)
    tracker.mark_signal(123, ts=t1 + 0.001)
    t3 = tracker.mark_order_send(event_id="order-1", t1=t1, t2=t1 + 0.001)
    tracker.mark_order_confirm(event_id="order-1", t1=t1, t2=t1 + 0.001, t3=t3)

    assert sink.events[-1]["stage"] == "T4"
    assert sink.events[-1]["end_to_end_ms"] >= 0
