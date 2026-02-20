import pytest
import asyncio
from unittest.mock import MagicMock
from ocpp.v16 import call, call_result
from chargeghost_evse.ocpp_adapter.adapter import Adapter

def test_on_get_configuration_empty_list():
    # Mock connection
    connection = MagicMock()
    adapter = Adapter("test_id", connection)
    
    # Test with key=None (omitted)
    result_none = asyncio.run(adapter.on_get_configuration(key=None))
    assert len(result_none.configuration_key) > 0
    
    # Test with key=[] (empty list)
    result_empty = asyncio.run(adapter.on_get_configuration(key=[]))
    assert len(result_empty.configuration_key) > 0, "Should return all keys when key list is empty"

def test_on_get_configuration_specific_keys():
    connection = MagicMock()
    adapter = Adapter("test_id", connection)
    
    # Test with specific key
    result = asyncio.run(adapter.on_get_configuration(key=["HeartbeatInterval"]))
    assert len(result.configuration_key) == 1
    assert result.configuration_key[0].key == "HeartbeatInterval"
    assert result.unknown_key is None

def test_on_get_configuration_unknown_keys():
    connection = MagicMock()
    adapter = Adapter("test_id", connection)
    
    # Test with unknown key
    result = asyncio.run(adapter.on_get_configuration(key=["NonExistentKey"]))
    assert len(result.configuration_key) == 0
    assert result.unknown_key == ["NonExistentKey"]
