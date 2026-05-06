"""Channel — persistent named conversation with unique slug."""

from .context import ChannelContextBuilder
from .models import ChannelData, ChannelSummary, validate_slug
from .store import ChannelStore
from .subscription import ChannelSubscriptionManager

__all__ = [
    "ChannelContextBuilder",
    "ChannelData",
    "ChannelSubscriptionManager",
    "ChannelSummary",
    "ChannelStore",
    "validate_slug",
]
