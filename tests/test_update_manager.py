from chargeghost_evse.util.update_manager import UpdateManager


def test_is_update_available_when_tag_is_newer():
	assert UpdateManager.is_update_available("0.1.0", "v0.2.0") is True


def test_is_update_not_available_when_same_version():
	assert UpdateManager.is_update_available("0.1.0", "v0.1.0") is False


def test_select_asset_for_macos_zip():
	assets = [
		{"name": "chargeghost-evse-macos.zip", "browser_download_url": "https://x/m.zip"},
		{"name": "chargeghost-evse-windows.zip", "browser_download_url": "https://x/w.zip"},
	]
	asset = UpdateManager.select_asset_for_platform("Darwin", assets)
	assert asset["browser_download_url"] == "https://x/m.zip"


def test_select_asset_for_windows_exe():
	assets = [
		{"name": "chargeghost-evse-macos.zip", "browser_download_url": "https://x/m.zip"},
		{"name": "chargeghost-evse-windows.exe", "browser_download_url": "https://x/w.exe"},
		{"name": "chargeghost-evse-windows.zip", "browser_download_url": "https://x/w.zip"},
	]
	asset = UpdateManager.select_asset_for_platform("Windows", assets)
	assert asset["browser_download_url"] == "https://x/w.exe"
