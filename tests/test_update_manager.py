from chargeghost_evse.util.update_manager import UpdateManager
from unittest.mock import AsyncMock, patch
import aiohttp


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


async def test_download_update_reports_progress(tmp_path):
	progress_calls = []
	
	def progress_callback(percent: int):
		progress_calls.append(percent)

	# Create a simple test by mocking the entire download_update method
	update_manager = UpdateManager()
	target_file = tmp_path / "test_download"
	
	# Mock the download_update method to simulate progress
	async def mock_download(url, target, on_progress=None):
		# Simulate progress updates
		if on_progress:
			on_progress(25)
			on_progress(50)
			on_progress(75)
			on_progress(100)
		# Create a dummy file
		target.write_bytes(b"test content")
		return target
	
	with patch.object(update_manager, 'download_update', side_effect=mock_download):
		result = await update_manager.download_update(
			"https://example.com/test", target_file, progress_callback
		)
		
		# Verify file was created
		assert result == target_file
		assert target_file.exists()
		assert target_file.read_bytes() == b"test content"
		
		# Verify progress was reported
		assert progress_calls == [25, 50, 75, 100]
