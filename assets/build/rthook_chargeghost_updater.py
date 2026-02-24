"""
Runtime hook for ChargeGhost EVSE to ensure updater functionality works in frozen builds.
"""

import sys
import os

# Add updater-specific runtime configurations
if getattr(sys, 'frozen', False):
    # Enable updater logging in production builds
    os.environ['CHARGEGHOST_UPDATER_ENABLED'] = '1'

    # Set up proper temp directory for handover scripts
    import tempfile
    os.environ['CHARGEGHOST_TEMP_DIR'] = tempfile.gettempdir()
