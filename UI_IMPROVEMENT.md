# UI/UX Improvement Proposals - ChargeGhost EVSE

This document outlines a series of UI and UX enhancements for the ChargeGhost EVSE simulator. These proposals aim to improve the professional look, usability, and maintainability of the application.

## 1. Navigation & Workflow Enhancements

### 1.1 Global Navigation "Back" Button
*   **Issue:** Once a user enters "Simulator Mode" or "Manual Mode", there is no way to return to the initial "Mode Select" screen without restarting the application.
*   **Proposal:** Add a "Home" or "Back" icon/button in the top-left corner or within the status bar to allow switching between modes easily.

### 1.2 Sidebar Navigation Pattern
*   **Issue:** The current top-tab navigation (Dashboard/Settings) is functional but limits scalability as more features are added (e.g., Reports, Logs, Maintenance).
*   **Proposal:** Transition to a collapsible sidebar navigation. This provides more room for labels and sub-navigation items.

### 1.3 Unified Log Panel
*   **Issue:** `CollapsibleLogPanel` is duplicated across different tabs.
*   **Proposal:** Implement a single, global Log Panel that can be toggled from any screen (using a shortcut like `` ` `` or a button in the status bar). This keeps the logs persistent as the user navigates between tabs.

## 2. Dashboard & Visualization

### 2.1 Live Simulation Charts
*   **Issue:** Power, Voltage, and Current are shown as static numbers. It's hard to visualize the "history" of a charging session.
*   **Proposal:** Add a small "Sparkline" or a full real-time chart (using `QtCharts` or `pyqtgraph`) to the Dashboard to show power delivery over time.

### 2.2 SVG Icon Integration
*   **Issue:** Many status indicators use emojis (🟢, ⚡, 🔌). While functional, they can look inconsistent across different operating systems.
*   **Proposal:** Replace emojis with a consistent set of SVG icons (e.g., from Lucide or FontAwesome). Standardize these in the `e_mobility.qss` file.

### 2.3 Interactive Connector Strip
*   **Issue:** The `ConnectorStrip` is quite basic.
*   **Proposal:** Enhance the connector indicators with more visual feedback:
    *   A pulsing animation when charging.
    *   Better visual distinction between "Selected" and "Active" (charging).
    *   Tooltips showing quick stats on hover.

### 2.4 Smart ID Tag Management
*   **Issue:** Users have to manually type ID Tags every time.
*   **Proposal:** Add a "Recent Tags" dropdown next to the ID Tag input to allow quick selection of previously used tags.

## 3. Settings & Configuration

### 3.1 Styling Standardization
*   **Issue:** Several widgets (`StatusPanel`, `ConnectorEditorCard`) use inline `setStyleSheet` calls. This makes theming difficult and leads to visual inconsistencies.
*   **Proposal:** Move all hardcoded styles into the `e_mobility.qss` file. Use `setObjectName` or dynamic properties (e.g., `setProperty("type", "header")`) to target elements.

### 3.2 OCPP Key Categorization
*   **Issue:** All OCPP configuration keys are shown in a single long list.
*   **Proposal:** Group keys by their OCPP functional blocks (Core, Smart Charging, Reservation, Local Auth List) using collapsible sections or a search filter.

### 3.3 Input Validation Feedback
*   **Issue:** There is minimal visual feedback for invalid configuration inputs (e.g., malformed WebSocket URL).
*   **Proposal:** Implement real-time validation feedback (e.g., red border for invalid fields, helper text below the input).

## 4. Visual Polish & Micro-interactions

### 4.1 State Transition Animations
*   **Issue:** UI updates are "instant" and can feel jumpy.
*   **Proposal:** Add subtle fade-in/out transitions when switching between dashboard states (e.g., when a session starts).

### 4.2 Toast Notifications
*   **Issue:** Critical feedback (errors, successful saves) is only visible if the log panel is expanded.
*   **Proposal:** Implement "Toast" style notifications that appear briefly at the top/bottom of the screen for important events like "Configuration Saved" or "OCPP Connection Lost".

### 4.3 Improved Empty States
*   **Issue:** Screens with no active data (e.g., no connectors added) can look "broken" or confusing.
*   **Proposal:** Design dedicated "Empty State" views with helpful instructions or an "Add First Connector" call-to-action button.

## 5. Technical Improvements for UI

*   **Move to QSettings:** Instead of manual YAML saving for every minor change, use `QSettings` for UI-specific state (window size, log panel expansion, last selected connector).
*   **High-DPI Support:** Explicitly enable High-DPI scaling in the `main()` function to ensure the UI looks sharp on 4K monitors.
*   **Keyboard Shortcuts:** Add shortcuts for common actions (e.g., `Ctrl+S` to save config, `F1` for logs).
