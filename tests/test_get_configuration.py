import asyncio
from unittest.mock import MagicMock
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

def test_message_timeout_is_in_configuration_keys():
    connection = MagicMock()
    adapter = Adapter("test_id", connection)
    
    result = asyncio.run(adapter.on_get_configuration(key=["MessageTimeout"]))
    assert len(result.configuration_key) == 1
    assert result.configuration_key[0].key == "MessageTimeout"
    assert result.configuration_key[0].value == "30"

def test_change_configuration_message_timeout_updates_response_timeout():
    connection = MagicMock()
    adapter = Adapter("test_id", connection, response_timeout=30)
    
    assert adapter.response_timeout == 30
    
    result = asyncio.run(adapter.on_change_configuration(key="MessageTimeout", value="60"))
    assert result.status.value == "Accepted"
    assert adapter.response_timeout == 60
