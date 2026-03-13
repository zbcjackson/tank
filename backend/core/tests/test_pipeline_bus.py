"""Tests for Bus (message bus)."""


from tank_backend.pipeline.bus import Bus, BusMessage


class TestBusMessage:
    def test_bus_message_init(self):
        """BusMessage should initialize with type, source, payload."""
        msg = BusMessage(type="test", source="proc1", payload={"key": "value"})
        assert msg.type == "test"
        assert msg.source == "proc1"
        assert msg.payload == {"key": "value"}
        assert isinstance(msg.timestamp, float)

    def test_bus_message_default_payload(self):
        """BusMessage payload should default to None."""
        msg = BusMessage(type="test", source="proc1")
        assert msg.payload is None


class TestBus:
    def test_bus_post_and_poll(self):
        """Bus should queue messages and dispatch on poll."""
        bus = Bus()
        received = []

        def handler(msg: BusMessage):
            received.append(msg)

        bus.subscribe("test_type", handler)
        bus.post(BusMessage(type="test_type", source="proc1", payload="data1"))
        bus.post(BusMessage(type="test_type", source="proc2", payload="data2"))

        # Messages not dispatched until poll
        assert len(received) == 0

        count = bus.poll()
        assert count == 2
        assert len(received) == 2
        assert received[0].payload == "data1"
        assert received[1].payload == "data2"

    def test_bus_multiple_subscribers(self):
        """Multiple subscribers should all receive messages."""
        bus = Bus()
        received1 = []
        received2 = []

        bus.subscribe("test", lambda msg: received1.append(msg))
        bus.subscribe("test", lambda msg: received2.append(msg))

        bus.post(BusMessage(type="test", source="proc1"))
        bus.poll()

        assert len(received1) == 1
        assert len(received2) == 1

    def test_bus_type_filtering(self):
        """Subscribers should only receive messages of subscribed type."""
        bus = Bus()
        received_a = []
        received_b = []

        bus.subscribe("type_a", lambda msg: received_a.append(msg))
        bus.subscribe("type_b", lambda msg: received_b.append(msg))

        bus.post(BusMessage(type="type_a", source="proc1"))
        bus.post(BusMessage(type="type_b", source="proc2"))
        bus.poll()

        assert len(received_a) == 1
        assert len(received_b) == 1
        assert received_a[0].type == "type_a"
        assert received_b[0].type == "type_b"

    def test_bus_handler_exception_does_not_crash(self):
        """Bus should handle exceptions in handlers gracefully."""
        bus = Bus()
        received = []

        def bad_handler(msg):
            raise ValueError("Handler error")

        def good_handler(msg):
            received.append(msg)

        bus.subscribe("test", bad_handler)
        bus.subscribe("test", good_handler)

        bus.post(BusMessage(type="test", source="proc1"))
        count = bus.poll()

        # Good handler should still run despite bad handler exception
        assert len(received) == 1
        # Count only includes successful handler invocations
        assert count == 1

    def test_bus_poll_clears_pending(self):
        """Bus.poll should clear pending messages after dispatch."""
        bus = Bus()
        received = []

        bus.subscribe("test", lambda msg: received.append(msg))
        bus.post(BusMessage(type="test", source="proc1"))

        bus.poll()
        assert len(received) == 1

        # Second poll should not re-dispatch
        bus.poll()
        assert len(received) == 1

    def test_bus_thread_safety(self):
        """Bus should be thread-safe for post/poll."""
        import threading

        bus = Bus()
        received = []

        bus.subscribe("test", lambda msg: received.append(msg))

        def poster():
            for i in range(10):
                bus.post(BusMessage(type="test", source=f"thread_{i}"))

        threads = [threading.Thread(target=poster) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        bus.poll()
        assert len(received) == 50  # 5 threads * 10 messages each
