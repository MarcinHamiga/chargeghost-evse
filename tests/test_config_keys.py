from chargeghost_evse.ocpp_adapter.config_keys import ConfigurationKeyManager
from ocpp.v16.enums import ConfigurationStatus

def test_initialize_defaults():
    manager = ConfigurationKeyManager()
    manager.initialize_defaults()
    
    # Check some mandatory keys
    assert manager.get_key("HeartbeatInterval") is not None
    assert manager.get_key("MeterValueSampleInterval") is not None
    assert manager.get_key("ConnectionTimeout") is not None
    assert manager.get_key("SupportedFeatureProfiles") is not None
    
    # Check default values
    assert manager.get_int_value("HeartbeatInterval") == 300
    assert manager.get_int_value("MeterValueSampleInterval") == 60
    assert manager.get_int_value("ConnectionTimeout") == 30

def test_set_key_updates_value():
    manager = ConfigurationKeyManager()
    manager.initialize_defaults()
    
    status = manager.set_key("HeartbeatInterval", "600")
    assert status == ConfigurationStatus.accepted
    assert manager.get_int_value("HeartbeatInterval") == 600

def test_set_readonly_key_fails():
    manager = ConfigurationKeyManager()
    manager.initialize_defaults()
    
    # NumberOfConnectors is readonly
    status = manager.set_key("NumberOfConnectors", "2")
    assert status == ConfigurationStatus.rejected
    assert manager.get_int_value("NumberOfConnectors") == 1

def test_set_non_existent_key_fails():
    manager = ConfigurationKeyManager()
    manager.initialize_defaults()
    
    status = manager.set_key("NonExistentKey", "Value")
    assert status == ConfigurationStatus.not_supported

def test_key_changed_event():
    manager = ConfigurationKeyManager()
    manager.initialize_defaults()
    
    events = []
    def on_change(key_name, new_value):
        events.append((key_name, new_value))
        
    manager.on_key_changed.subscribe(on_change)
    manager.set_key("MeterValueSampleInterval", "30")
    
    assert len(events) == 1
    assert events[0] == ("MeterValueSampleInterval", "30")

def test_get_bool_value():
    manager = ConfigurationKeyManager()
    manager.initialize_defaults()
    
    manager.set_key("LocalAuthListEnabled", "true")
    assert manager.get_bool_value("LocalAuthListEnabled") is True
    
    manager.set_key("LocalAuthListEnabled", "false")
    assert manager.get_bool_value("LocalAuthListEnabled") is False
    
    manager.set_key("LocalAuthListEnabled", "1")
    assert manager.get_bool_value("LocalAuthListEnabled") is True
