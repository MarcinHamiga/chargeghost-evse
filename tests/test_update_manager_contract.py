def test_release_asset_contract_names_are_supported():
	"""Test that asset name patterns match documented expectations."""
	from chargeghost_evse.util.update_manager import UpdateManager
	
	# Test Windows patterns
	windows_assets = [
		{"name": "chargeghost-evse-windows.exe", "browser_download_url": "https://example.com/windows.exe"},
		{"name": "chargeghost-evse-windows.zip", "browser_download_url": "https://example.com/windows.zip"},
		{"name": "chargeghost-evse-macos.zip", "browser_download_url": "https://example.com/macos.zip"},
	]
	
	# Should prefer .exe over .zip for Windows
	asset = UpdateManager.select_asset_for_platform("Windows", windows_assets)
	assert asset["name"] == "chargeghost-evse-windows.exe"
	
	# Test macOS patterns
	macos_assets = [
		{"name": "chargeghost-evse-macos.zip", "browser_download_url": "https://example.com/macos.zip"},
		{"name": "chargeghost-evse-windows.exe", "browser_download_url": "https://example.com/windows.exe"},
		{"name": "chargeghost-evse.dmg", "browser_download_url": "https://example.com/app.dmg"},
	]
	
	# Should prefer .dmg over .zip for macOS
	asset = UpdateManager.select_asset_for_platform("Darwin", macos_assets)
	assert asset["name"] == "chargeghost-evse.dmg"
	
	# Test when no matching asset
	asset = UpdateManager.select_asset_for_platform("Linux", windows_assets)
	assert asset is None
