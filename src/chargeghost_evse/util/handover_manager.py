"""
Application Handover Manager Module.

This module provides functionality for self-updating the application by
coordinating the replacement of the running executable with a new version.
It handles the platform-specific details of waiting for the old process
to exit, replacing the binary, and restarting the application.

The handover process:
1. Download new version to a temporary location
2. Create a platform-specific script to handle the swap
3. Launch the script in a separate process
4. Current application exits
5. Script waits for the old process to terminate
6. Script replaces old binary with new one
7. Script launches the new version

Classes:
    HandoverManager: Manages the application handover process.

Supported Platforms:
    - Windows: Uses batch script with tasklist monitoring
    - macOS: Uses bash script with kill signal monitoring
"""

import platform
import subprocess
from pathlib import Path


class HandoverManager:
    """
    Manages application self-update handover process.

    Creates and launches platform-specific scripts that wait for the
    current process to exit, replace the executable, and restart.

    Attributes:
        temp_dir: Directory for temporary script files.

    Example:
        >>> from pathlib import Path
        >>> manager = HandoverManager(Path("/tmp/chargeghost"))
        >>> 
        >>> # Create handover script
        >>> script = manager.build_macos_script(
        ...     pid=12345,
        ...     new_path="/tmp/ChargeGhost-new.app",
        ...     old_path="/Applications/ChargeGhost.app"
        ... )
        >>> 
        >>> # Launch handover (then exit current process)
        >>> script_path = Path("/tmp/chargeghost/handover.sh")
        >>> script_path.write_text(script)
        >>> manager.launch_handover(script_path)
    """

    def __init__(self, temp_dir: Path) -> None:
        """
        Initialize the handover manager.

        Args:
            temp_dir: Directory for storing temporary script files.
                Should be a location that persists after app exit.
        """
        self.temp_dir = temp_dir

    def build_windows_script(self, pid: int, new_path: str, old_path: str) -> str:
        """
        Build a Windows batch script for the handover process.

        The script:
        1. Waits for the process with given PID to terminate
        2. Moves the new executable to replace the old one
        3. Starts the new executable
        4. Deletes itself

        Args:
            pid: Process ID of the current running instance.
            new_path: Path to the new executable/app bundle.
            old_path: Path to the old executable/app bundle to replace.

        Returns:
            Batch script content as a string.
        """
        return f"""@echo off
set "TARGET_PID={pid}"
set "NEW_EXE={new_path}"
set "OLD_EXE={old_path}"
:wait
tasklist /FI "PID eq %TARGET_PID%" | find ":" > nul
if %errorlevel% neq 0 (
	move /y "%NEW_EXE%" "%OLD_EXE%"
	start "" "%OLD_EXE%"
	del "%~f0"
	exit
)
timeout /t 1 /nobreak > nul
goto wait
"""

    def build_macos_script(self, pid: int, new_path: str, old_path: str) -> str:
        """
        Build a macOS bash script for the handover process.

        The script:
        1. Waits for the process with given PID to terminate
        2. Removes the old app bundle
        3. Moves the new app bundle to the old location
        4. Opens the new app
        5. Deletes itself

        Args:
            pid: Process ID of the current running instance.
            new_path: Path to the new app bundle (.app).
            old_path: Path to the old app bundle to replace.

        Returns:
            Bash script content as a string.
        """
        return f"""#!/bin/bash
PID={pid}
NEW_APP_PATH="{new_path}"
OLD_APP_PATH="{old_path}"
while kill -0 $PID 2>/dev/null; do sleep 1; done
rm -rf "$OLD_APP_PATH"
mv "$NEW_APP_PATH" "$OLD_APP_PATH"
open "$OLD_APP_PATH"
rm "$0"
"""

    def launch_handover(self, script_path: Path) -> None:
        """
        Launch the handover script in a separate process.

        The script runs independently and continues after the current
        process exits. Platform-specific handling ensures proper
        process detachment.

        Args:
            script_path: Path to the handover script file.

        Note:
            On Windows, the script is run via cmd.exe.
            On Unix-like systems, the script is made executable first.
        """
        if platform.system() == "Windows":
            # Windows: Run batch script via cmd in new session
            subprocess.Popen(["cmd", "/c", str(script_path)], start_new_session=True)
        else:
            # macOS/Linux: Make script executable and run in new session
            script_path.chmod(0o755)
            subprocess.Popen([str(script_path)], start_new_session=True)
