@echo off
REM PyMate Launcher (pymate.bat)
REM This script runs the PyMate Python tool and applies any environment
REM changes it prepares for the current CMD session.

SETLOCAL ENABLEDELAYEDEXPANSION

REM Get the directory of this batch script
SET "SCRIPT_DIR=%~dp0"
SET "PYTHON_SCRIPT_PATH=%SCRIPT_DIR%PyMate.py"
REM Ensure TEMP path is valid, fallback if not (less common issue)
IF NOT DEFINED TEMP (SET "TEMP=%USERPROFILE%\AppData\Local\Temp")
IF NOT EXIST "%TEMP%\" ( MKDIR "%TEMP%" >NUL 2>NUL )
SET "ENV_SETUP_SCRIPT=%TEMP%\pymate_env_setup.bat"


REM Clean up old setup script if it exists (e.g., from a previous crashed session)
IF EXIST "%ENV_SETUP_SCRIPT%" (
    DEL "%ENV_SETUP_SCRIPT%" >NUL 2>NUL
)

REM Check if PyMate.py exists
IF NOT EXIST "%PYTHON_SCRIPT_PATH%" (
    echo ERROR: PyMate.py not found at "%PYTHON_SCRIPT_PATH%"
    echo Please ensure PyMate.py is in the same directory as pymate.bat.
    pause
    goto :eof
)

REM --- Run PyMate.py ---
REM The Python script will handle its own admin elevation if needed.
REM Use Python Launcher `py.exe` if available
py -3 "%PYTHON_SCRIPT_PATH%" %*
IF !ERRORLEVEL! EQU 0 GOTO PyMateCallSuccessful
IF !ERRORLEVEL! EQU 9009 (
    echo 'py.exe' (Python Launcher) not found or not in PATH. Trying 'python.exe'...
    python "%PYTHON_SCRIPT_PATH%" %*
    IF !ERRORLEVEL! EQU 0 GOTO PyMateCallSuccessful
    IF !ERRORLEVEL! EQU 9009 (
        echo 'python.exe' also not found in PATH. Cannot run PyMate.
        echo Please ensure you have a Python accessible in your PATH, or install the Python Launcher (py.exe).
        pause
        goto :eof
    ) ELSE (
        echo PyMate.py exited with error code !ERRORLEVEL!.
    )
) ELSE (
     REM Special exit code 99 from PyMate means it self-elevated, parent should terminate.
    IF !ERRORLEVEL! EQU 99 (
        REM echo PyMate self-elevated. Parent batch terminating.
        goto :eof
    )
    echo PyMate.py exited with error code !ERRORLEVEL!.
)

:PyMateCallSuccessful
REM echo PyMate.py execution finished successfully from batch perspective.

:HandleEnvSetup
REM If PyMate.py created an environment setup script (for CURRENT SESSION changes), execute it.
IF EXIST "%ENV_SETUP_SCRIPT%" (
    echo Applying environment changes from PyMate for this session...
    call "%ENV_SETUP_SCRIPT%"
    DEL "%ENV_SETUP_SCRIPT%" >NUL 2>NUL
    echo Environment changes applied for this session.
)

ENDLOCAL
echo PyMate tasks complete. Continue in this CMD session.