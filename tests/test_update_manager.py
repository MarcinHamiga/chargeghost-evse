from chargeghost_evse.util.update_manager import UpdateManager


def test_is_update_available_when_tag_is_newer():
	assert UpdateManager.is_update_available("0.1.0", "v0.2.0") is True


def test_is_update_not_available_when_same_version():
	assert UpdateManager.is_update_available("0.1.0", "v0.1.0") is False
