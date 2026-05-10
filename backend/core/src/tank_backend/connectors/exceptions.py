"""Connector framework exceptions."""

from __future__ import annotations


class ConnectorError(Exception):
    """Base class for connector framework errors."""


class DuplicateConnectorError(ConnectorError):
    """Two connector instances share the same ``instance_name``."""


class UnknownConnectorError(ConnectorError):
    """A config references a connector that is not in the registry."""
