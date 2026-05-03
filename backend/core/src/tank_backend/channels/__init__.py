"""Channel — persistent named conversation with unique slug."""

from .context import ChannelContextBuilder
from .models import ChannelData, ChannelSummary, validate_slug
from .store import ChannelStore

__all__ = [
    "ChannelContextBuilder",
    "ChannelData",
    "ChannelSummary",
    "ChannelStore",
    "validate_slug",
]
