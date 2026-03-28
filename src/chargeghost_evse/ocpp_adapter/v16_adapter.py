"""
OCPP 1.6 Adapter Module.

This module provides the OCPP 1.6 adapter implementation. The actual adapter
implementation is in adapter.py. This module exists to support the versioned
adapter factory pattern.
"""

from chargeghost_evse.ocpp_adapter.adapter import Adapter

V16Adapter = Adapter

__all__ = ["V16Adapter", "Adapter"]
