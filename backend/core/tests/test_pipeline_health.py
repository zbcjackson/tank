"""Tests for pipeline health dataclasses and HealthAggregator."""


from tank_backend.pipeline.health import (
    ComponentHealth,
    HealthAggregator,
    PipelineHealth,
    ProcessorHealth,
    QueueHealth,
)


class TestQueueHealth:
    def test_frozen(self):
        """QueueHealth should be immutable."""
        qh = QueueHealth(
            name="q_0",
            size=3,
            maxsize=10,
            last_consumed_at=100.0,
            is_stuck=False,
            consumer_alive=True,
        )
        assert qh.name == "q_0"
        assert qh.size == 3
        assert qh.maxsize == 10
        assert qh.is_stuck is False
        assert qh.consumer_alive is True

    def test_stuck_queue(self):
        """QueueHealth should report stuck state."""
        qh = QueueHealth(
            name="q_stuck",
            size=5,
            maxsize=10,
            last_consumed_at=1.0,
            is_stuck=True,
            consumer_alive=True,
        )
        assert qh.is_stuck is True


class TestProcessorHealth:
    def test_healthy_processor(self):
        ph = ProcessorHealth(
            name="vad", is_running=True, consecutive_failures=0, last_error=None
        )
        assert ph.is_running is True
        assert ph.consecutive_failures == 0

    def test_failing_processor(self):
        ph = ProcessorHealth(
            name="asr", is_running=True, consecutive_failures=3, last_error="timeout"
        )
        assert ph.consecutive_failures == 3
        assert ph.last_error == "timeout"


class TestPipelineHealth:
    def test_healthy_pipeline(self):
        ph = PipelineHealth(
            running=True, processors=[], queues=[], is_healthy=True
        )
        assert ph.is_healthy is True

    def test_unhealthy_pipeline(self):
        qh = QueueHealth(
            name="q_0", size=5, maxsize=10,
            last_consumed_at=1.0, is_stuck=True, consumer_alive=True,
        )
        ph = PipelineHealth(
            running=True, processors=[], queues=[qh], is_healthy=False
        )
        assert ph.is_healthy is False


class TestComponentHealth:
    def test_defaults(self):
        ch = ComponentHealth(name="pipeline", status="healthy", detail="All good")
        assert ch.name == "pipeline"
        assert ch.status == "healthy"
        assert ch.checked_at > 0


class TestHealthAggregator:
    def test_empty(self):
        agg = HealthAggregator()
        result = agg.check_all()
        assert result["status"] == "healthy"
        assert result["components"] == {}

    def test_single_healthy(self):
        agg = HealthAggregator()
        agg.register(
            "pipeline",
            lambda: ComponentHealth(name="pipeline", status="healthy", detail="ok"),
        )
        result = agg.check_all()
        assert result["status"] == "healthy"
        assert result["components"]["pipeline"]["status"] == "healthy"

    def test_degraded(self):
        agg = HealthAggregator()
        agg.register(
            "pipeline",
            lambda: ComponentHealth(name="pipeline", status="healthy", detail="ok"),
        )
        agg.register(
            "llm",
            lambda: ComponentHealth(name="llm", status="degraded", detail="slow"),
        )
        result = agg.check_all()
        assert result["status"] == "degraded"

    def test_unhealthy_overrides_degraded(self):
        agg = HealthAggregator()
        agg.register(
            "a",
            lambda: ComponentHealth(name="a", status="degraded", detail="slow"),
        )
        agg.register(
            "b",
            lambda: ComponentHealth(name="b", status="unhealthy", detail="dead"),
        )
        result = agg.check_all()
        assert result["status"] == "unhealthy"

    def test_check_exception_reports_unhealthy(self):
        def bad_check():
            raise RuntimeError("boom")

        agg = HealthAggregator()
        agg.register("broken", bad_check)
        result = agg.check_all()
        assert result["status"] == "unhealthy"
        assert "exception" in result["components"]["broken"]["detail"].lower()

    def test_is_healthy_always_true(self):
        """is_healthy is a fast liveness check, always returns True."""
        agg = HealthAggregator()
        assert agg.is_healthy() is True
