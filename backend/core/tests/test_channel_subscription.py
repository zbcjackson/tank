"""Tests for ChannelSubscriptionManager."""

import pytest

from tank_backend.channels.subscription import ChannelSubscriptionManager


@pytest.fixture
def mgr() -> ChannelSubscriptionManager:
    return ChannelSubscriptionManager()


class TestSubscribe:
    def test_subscribe_single_channel(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.subscribe("s1", ["daily-report"])
        assert mgr.get_subscribers("daily-report") == {"s1"}
        assert mgr.get_subscriptions("s1") == {"daily-report"}

    def test_subscribe_multiple_channels(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.subscribe("s1", ["ch-a", "ch-b"])
        assert mgr.get_subscriptions("s1") == {"ch-a", "ch-b"}
        assert mgr.get_subscribers("ch-a") == {"s1"}
        assert mgr.get_subscribers("ch-b") == {"s1"}

    def test_multiple_sessions_same_channel(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.subscribe("s1", ["news"])
        mgr.subscribe("s2", ["news"])
        assert mgr.get_subscribers("news") == {"s1", "s2"}

    def test_subscribe_idempotent(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.subscribe("s1", ["ch"])
        mgr.subscribe("s1", ["ch"])
        assert mgr.get_subscribers("ch") == {"s1"}


class TestUnsubscribe:
    def test_unsubscribe_removes_mapping(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.subscribe("s1", ["ch-a", "ch-b"])
        mgr.unsubscribe("s1", ["ch-a"])
        assert mgr.get_subscriptions("s1") == {"ch-b"}
        assert mgr.get_subscribers("ch-a") == set()

    def test_unsubscribe_all_cleans_session(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.subscribe("s1", ["ch"])
        mgr.unsubscribe("s1", ["ch"])
        assert mgr.get_subscriptions("s1") == set()

    def test_unsubscribe_nonexistent_session(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.unsubscribe("ghost", ["ch"])  # should not raise

    def test_unsubscribe_nonexistent_channel(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.subscribe("s1", ["ch-a"])
        mgr.unsubscribe("s1", ["ch-b"])  # should not raise
        assert mgr.get_subscriptions("s1") == {"ch-a"}


class TestRemoveSession:
    def test_remove_cleans_both_directions(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.subscribe("s1", ["ch-a", "ch-b"])
        mgr.subscribe("s2", ["ch-a"])
        mgr.remove_session("s1")
        assert mgr.get_subscriptions("s1") == set()
        assert mgr.get_subscribers("ch-a") == {"s2"}
        assert mgr.get_subscribers("ch-b") == set()

    def test_remove_nonexistent_session(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.remove_session("ghost")  # should not raise


class TestGetSubscribers:
    def test_returns_copy(self, mgr: ChannelSubscriptionManager) -> None:
        mgr.subscribe("s1", ["ch"])
        subs = mgr.get_subscribers("ch")
        subs.add("s99")
        assert mgr.get_subscribers("ch") == {"s1"}

    def test_empty_for_unknown_channel(self, mgr: ChannelSubscriptionManager) -> None:
        assert mgr.get_subscribers("unknown") == set()
