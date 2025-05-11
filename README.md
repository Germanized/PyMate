# PyMate By Germanized - Python Environment Manager

**Version:** 1.0.0

PyMate is a comprehensive command-line tool designed to simplify the management of multiple Python installations and enhance your Python development workflow, primarily on Windows but with considerations for other platforms.

## Features

### Core Python Version Management
*   **Scan for Installations:** Automatically detects Python versions installed on your system.
    *   Windows: Utilizes `py -0p` (Python Launcher) and `where python`.
    *   Linux/macOS: Uses `which -a python3/python`.
*   **Session Python Switching:** Temporarily set a specific Python version to be active in your current command prompt session.
    *   Modifies `PATH` for the session.
    *   Sets `PYMATE_ACTIVE_PYTHON_PATH` and `PYMATE_ACTIVE_PYTHON_VERSION` environment variables.
    *   Adds session-specific aliases (e.g., `python`, `pip` pointing to the selected version).
*   **Persistent Default Python (Windows):**
    *   Set a User-level default Python.
    *   Set a System-level default Python (requires Administrator privileges).
    *   Manages `PATH` in the Windows Registry.
    *   Stores its changes for clean reversion.
*   **Revert Persistent Changes (Windows):** Easily undo PyMate's persistent PATH modifications.
*   **Ensure PyMate Scripts in PATH (Windows):** Add PyMate's own helper script directory to the User or System PATH persistently.

### Advanced Quality of Life (QoL) Features
*   **Activate Virtual Environment:** Detects and offers to activate common virtual environments (`.venv`, `venv`, `env`) found in the current working directory (session-specific activation for Windows).
*   **Install Common Tools:** Quickly install popular Python packages like `rich`, `httpie`, `ipython`, `black`, `flake8`, `isort`, `pytest`, `pipx` using the currently active Python.
*   **Configure PYTHONSTARTUP:**
    *   Create or specify a `.pythonrc.py` file to be executed when the Python REPL starts.
    *   Set the `PYTHONSTARTUP` environment variable for the current session or persistently (User/System on Windows).
*   **Setup PyMate Helper Scripts (Windows .bat files):**
    *   Generate `.bat` helper scripts in a dedicated PyMate directory (e.g., `pyweb` for `python -m http.server`, `pyjupyter`, `pyipython`, `pytestrun`).
*   **Manage pip Cache:** View pip cache information/directory and purge the cache using the active Python.
*   **Install/Setup pipx:** Install `pipx` (for isolated CLI tool execution) and run `pipx ensurepath` if needed.
*   **Set Default pip Config (Global):** Interactively configure global `pip.ini` (Windows) or `pip.conf` (Linux/macOS) settings, e.g., toggling `no-cache-dir`. (Currently simplified, full INI modification would use `configparser`).
*   **Add User Scripts to PATH (Windows, Session):** Temporarily add Python User Scripts directories (e.g., `%APPDATA%\Python\PythonXX\Scripts`) to the PATH for the current session.
*   **Project Template Initializer (Cookiecutter):**
    *   Install `cookiecutter` if not found.
    *   Run `cookiecutter` with a provided template URL to initialize a new project.
*   **Toggleable Session Features:**
    *   Enable/Disable colored logging output (`PYTHON_COLOR=1`, `FORCE_COLOR=1`).
    *   Enable/Disable `py` alias for `python.exe` (Windows session).

### General Features
*   **Administrator Privileges:** Automatically attempts to re-launch with admin rights when required for persistent system changes (Windows).
*   **User-Friendly Interface:** Styled menus with ANSI TrueColor gradients and clear prompts (best viewed in modern terminals like Windows Terminal).
*   **Configuration Persistence:** Saves states of enabled advanced features and managed PATH entries in `APPDATA\PyMate` (Windows) or `.config/PyMate` (Linux/macOS).

## Prerequisites

*   **Python:** One or more Python versions installed.
*   **Windows:**
    *   Windows Terminal (recommended for best visual experience).
    *   Python Launcher (`py.exe`) is recommended for optimal discovery but PyMate will fallback.
*   **pip:** Required for package installation features; usually comes with Python.

## Installation / Setup

1.  **Download Files:**
    *   Save the `PyMate.py` Python script.
    *   Save the `pymate.bat` batch script *in the same directory* as `PyMate.py`.
2.  **No Formal Installation Needed:** The tool is run directly from these two files.
3.  **Optional: Add to PATH:** For convenience, you can add the directory containing `pymate.bat` to your system's PATH environment variable, so you can run `pymate` from any location. PyMate itself also has a feature to add its own generated helper scripts to the PATH.

## Usage

1.  **Open Command Prompt:**
    *   On Windows, open Command Prompt (CMD) or Windows Terminal.
    *   On Linux/macOS, open your preferred terminal.
2.  **Navigate to Directory:** If PyMate's directory is not in your PATH, `cd` to the directory where you saved `pymate.bat` and `PyMate.py`.
3.  **Run PyMate:**
    *   Execute the batch script: `pymate.bat` (or just `pymate` if its directory is in your PATH).
4.  **Follow On-Screen Menus:**
    *   **`S` - Scan:** Always a good first step to ensure PyMate sees all your Pythons.
    *   **`1` - Set Session Python:** Changes which `python` is used for the current CMD window only.
    *   **`2` / `3` - Set Persistent Default (Windows):** Changes the default `python` for your User or the whole System. **Requires a new CMD window (or sometimes a reboot) to see the effect.**
    *   **`R` - Revert (Windows):** Undoes PyMate's persistent PATH changes.
    *   **`P` - Add PyMate Scripts to PATH (Windows):** Makes helper scripts generated by PyMate callable directly.
    *   **`A` - Advanced QoL Features:** Access the submenu for additional tools and configurations.
    *   **`Q` - Quit:** Exits PyMate.

### Important Notes for Persistent PATH Changes (Windows):
*   Persistent PATH modifications require PyMate to have **Administrator privileges**. It will attempt to self-elevate if necessary.
*   After making persistent PATH changes, you **MUST open a NEW command prompt window** for the changes to take effect. In some cases, a system reboot might be required for all applications to recognize the new PATH.
*   PyMate attempts to manage its PATH entries cleanly. You can always view your PATH variable by typing `echo %PATH%` in CMD or checking System Properties -> Environment Variables.

## How It Works

*   **`pymate.bat` (Windows):** The main launcher. It executes `PyMate.py`. After the Python script finishes, if `PyMate.py` has prepared a temporary batch file (`%TEMP%\pymate_env_setup.bat`) for *session-specific* environment changes (like PATH modification or aliases for the current CMD window), `pymate.bat` calls this temporary script.
*   **`PyMate.py`:** The core Python script containing all logic.
    *   Discovers Python installations.
    *   Handles user interaction through menus.
    *   For session changes: Generates commands in `pymate_env_setup.bat`.
    *   For persistent changes (Windows): Modifies the Windows Registry (User or System PATH) and stores a record of its changes in `%APPDATA%\PyMate\persistent_path.json` to allow for clean reversion.
    *   Manages its own configuration for advanced features in `%APPDATA%\PyMate\advanced_features.json`.

## Disclaimer

This tool modifies system environment variables and, on Windows, the Registry. While designed with care, always ensure you understand the changes being made. Incorrect modifications to your system PATH or Registry can lead to unexpected behavior or system instability. Use at your own risk. It's advisable to know how to manually check and edit your PATH if needed.

## Future Development / TODO

*   More robust INI parsing for pip configuration.
*   Extended cross-platform support for advanced features currently marked Windows-specific.
*   Option to install specific Python versions (e.g., via `python.org` or tools like `pyenv-win`).
*   Watchdog script feature for auto-reloading Python files on change.
*   Global linter/formatter installation and configuration.
