import os
import sys
import subprocess
import json
import platform
from pathlib import Path
import ctypes
import shutil # For file operations like rmdir

# Conditional import for Windows Registry operations
if platform.system() == "Windows":
    import winreg

# --- Constants and Configuration ---
APP_NAME = "PyMate"
VERSION = "1.0.0" # Updated version

# Configuration Directory (ensure it uses Path object)
if platform.system() == "Windows":
    CONFIG_DIR_BASE = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    USER_SCRIPTS_DIR_BASE = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
else: # Linux/macOS
    CONFIG_DIR_BASE = Path.home() / ".config"
    USER_SCRIPTS_DIR_BASE = Path.home() / ".local" # for bin, share

CONFIG_DIR = CONFIG_DIR_BASE / APP_NAME
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PYMATE_GENERATED_SCRIPTS_DIR = USER_SCRIPTS_DIR_BASE / APP_NAME / "scripts"
PYMATE_GENERATED_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

PERSISTENT_PATH_CONFIG_FILE = CONFIG_DIR / "persistent_path.json"
ADV_FEATURES_CONFIG_FILE = CONFIG_DIR / "advanced_features.json"

# Temp file for environment commands for current session
ENV_SETUP_FILENAME = "pymate_env_setup.bat" if platform.system() == "Windows" else "pymate_env_setup.sh"
TEMP_DIR_PATH = Path(os.environ.get("TEMP", Path.home() / ("AppData/Local/Temp" if platform.system() == "Windows" else "tmp")))
TEMP_DIR_PATH.mkdir(parents=True, exist_ok=True)
ENV_SETUP_SCRIPT = TEMP_DIR_PATH / ENV_SETUP_FILENAME

EXIT_CODE_RELAUNCH_ADMIN = 99

# --- ANSI Colors & Styling (from previous version) ---
class AnsiColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    TC_BLUE = "\033[38;2;60;120;255m"
    TC_TEAL = "\033[38;2;0;180;180m"
    TC_LIGHT_BLUE = "\033[38;2;100;180;255m"
    TC_VERY_LIGHT_BLUE = "\033[38;2;180;220;255m"
    TC_WHITE = "\033[38;2;220;220;220m"
    TC_GREY = "\033[38;2;150;150;150m"
    TC_GREEN = "\033[38;2;0;200;100m"
    TC_YELLOW = "\033[38;2;255;200;0m"
    TC_ORANGE = "\033[38;2;255;150;50m"
    TC_RED = "\033[38;2;255;80;80m"

    @staticmethod
    def gradient_text(text, color1_rgb, color2_rgb):
        output = []
        n = len(text)
        if n == 0: return ""
        if n == 1: return f"\033[38;2;{color1_rgb[0]};{color1_rgb[1]};{color1_rgb[2]}m{text}{AnsiColors.RESET}"
        for i, char in enumerate(text):
            if char == ' ': output.append(char); continue
            ratio = i / (n - 1) if n > 1 else 0
            r = int(color1_rgb[0] * (1 - ratio) + color2_rgb[0] * ratio)
            g = int(color1_rgb[1] * (1 - ratio) + color2_rgb[1] * ratio)
            b = int(color1_rgb[2] * (1 - ratio) + color2_rgb[2] * ratio)
            output.append(f"\033[38;2;{r};{g};{b}m{char}")
        output.append(AnsiColors.RESET)
        return "".join(output)

    @staticmethod
    def title(text): return f"{AnsiColors.BOLD}{AnsiColors.gradient_text(text, [60,120,255], [0,180,180])}{AnsiColors.RESET}"
    @staticmethod
    def menu_header(text): return f"{AnsiColors.BOLD}{AnsiColors.TC_VERY_LIGHT_BLUE}{text}{AnsiColors.RESET}"
    @staticmethod
    def menu_item(idx, text, detail=""): return f"  {AnsiColors.TC_ORANGE}{str(idx).ljust(2)}{AnsiColors.RESET}. {AnsiColors.TC_WHITE}{text}{AnsiColors.RESET}{AnsiColors.TC_GREY} {detail}{AnsiColors.RESET}"
    @staticmethod
    def prompt(text): return f"{AnsiColors.TC_TEAL}{text}{AnsiColors.RESET}"
    @staticmethod
    def success(text): return f"{AnsiColors.TC_GREEN}SUCCESS: {text}{AnsiColors.RESET}"
    @staticmethod
    def error(text): return f"{AnsiColors.BOLD}{AnsiColors.TC_RED}ERROR: {text}{AnsiColors.RESET}"
    @staticmethod
    def warning(text): return f"{AnsiColors.TC_YELLOW}WARNING: {text}{AnsiColors.RESET}"
    @staticmethod
    def info(text): return f"{AnsiColors.TC_LIGHT_BLUE}INFO: {text}{AnsiColors.RESET}"
    @staticmethod
    def input_prompt(text): return f"{AnsiColors.TC_TEAL}{text} > {AnsiColors.RESET}"

# --- Globals ---
discovered_pythons = []
internal_active_python_path = None # For current session selection state
adv_features_config = {} # To store state of enabled advanced features

# --- Utility, Admin, Discovery, Environment (largely from previous version) ---

def load_adv_features_config():
    global adv_features_config
    if ADV_FEATURES_CONFIG_FILE.exists():
        try:
            with open(ADV_FEATURES_CONFIG_FILE, 'r') as f:
                adv_features_config = json.load(f)
        except json.JSONDecodeError:
            adv_features_config = {} # Reset if corrupt
    else:
        adv_features_config = {}

def save_adv_features_config():
    try:
        with open(ADV_FEATURES_CONFIG_FILE, 'w') as f:
            json.dump(adv_features_config, f, indent=2)
    except IOError:
        print(AnsiColors.error("Could not save advanced features configuration."))

def is_admin():
    if platform.system() == "Windows":
        try: return ctypes.windll.shell32.IsUserAnAdmin()
        except: return False
    return True # Assume sudo or not relevant for PATH modifications elsewhere

def relaunch_as_admin():
    if platform.system() == "Windows":
        print(AnsiColors.info("This operation requires administrator privileges. Attempting to relaunch..."))
        script = os.path.abspath(sys.argv[0])
        params = subprocess.list2cmdline(sys.argv[1:])
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
            sys.exit(EXIT_CODE_RELAUNCH_ADMIN)
        except Exception as e:
            print(AnsiColors.error(f"Failed to relaunch as administrator: {e}"))
    else:
        print(AnsiColors.warning("Admin re-launch is Windows-specific. Please use sudo if needed."))
    return False

def run_command(command, capture_output=True, text=True, shell=False, check=False, encoding='utf-8', errors='replace', env=None, cwd=None):
    effective_env = os.environ.copy()
    if env: effective_env.update(env)
    try:
        process = subprocess.run(
            command, capture_output=capture_output, text=text, shell=shell,
            check=check, encoding=encoding, errors=errors, env=effective_env, cwd=cwd
        )
        return process
    except FileNotFoundError:
        return subprocess.CompletedProcess(command, 127, stdout="", stderr=f"Command not found: {command[0] if isinstance(command, list) else command}")
    except Exception as e:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=f"Failed to run command {command}: {e}")

def get_python_version_from_exe(exe_path):
    # (Identical to previous, using run_command)
    if not Path(exe_path).exists(): return "N/A (Not Found)"
    ver_result = run_command([str(exe_path), "--version"])
    if ver_result and ver_result.returncode == 0:
        output = (ver_result.stdout or ver_result.stderr).strip()
        return output.split(" ")[1] if " " in output else output
    return "Unknown"

def find_pythons_windows():
    # (Improved version from before)
    pythons_found = {}
    try:
        proc = run_command(["py", "-0p"])
        if proc and proc.returncode == 0 and proc.stdout:
            for line in proc.stdout.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("Installed") or not line.startswith("-"): continue
                try:
                    parts = line.split(None, 1)
                    if len(parts) < 2: continue
                    version_marker = parts[0].strip().replace("-V:","").replace("*","")
                    executable_path_str = parts[1].strip()
                    if not Path(executable_path_str).exists() and "python.exe" not in executable_path_str.lower():
                         idx = line.find(":\\") -1
                         if idx > 0 : executable_path_str = line[idx:]
                    exe_path = Path(executable_path_str)
                    if exe_path.exists() and "python.exe" in exe_path.name.lower():
                        resolved_path = exe_path.resolve()
                        version = get_python_version_from_exe(resolved_path)
                        name = f"Python {version} (Py Launcher: {version_marker})"
                        pythons_found[str(resolved_path)] = {'name': name, 'version': version, 'path': resolved_path, 'source': 'py_launcher'}
                except Exception: pass
    except Exception: pass

    try:
        for exe_name in ["python.exe", "python3.exe"]: # Could add python3.x later
            proc = run_command(["where", exe_name])
            if proc and proc.returncode == 0 and proc.stdout:
                for p_str in proc.stdout.strip().splitlines():
                    exe_path = Path(p_str.strip())
                    resolved_path = exe_path.resolve()
                    if resolved_path.exists() and str(resolved_path) not in pythons_found:
                        version = get_python_version_from_exe(resolved_path)
                        name = f"Python {version} (PATH: {exe_path.parent.name})"
                        pythons_found[str(resolved_path)] = {'name': name, 'version': version, 'path': resolved_path, 'source': 'where'}
    except Exception: pass
    return list(pythons_found.values())


def find_pythons_linux_mac():
    # (Identical to previous)
    pythons_found = {}
    for exe_name in ["python3", "python"]:
        proc = run_command(["which", "-a", exe_name]) # '-a' lists all matches in PATH
        if proc and proc.returncode == 0 and proc.stdout:
            for p_str in proc.stdout.strip().splitlines():
                try:
                    exe_path = Path(p_str.strip()).resolve()
                    if exe_path.exists() and str(exe_path) not in pythons_found:
                        version = get_python_version_from_exe(exe_path)
                        name = f"Python {version} ({exe_name} at {exe_path})"
                        pythons_found[str(exe_path)] = {'name': name, 'version': version, 'path': exe_path, 'source': 'which'}
                except Exception: continue
    return list(pythons_found.values())


def discover_pythons_and_update_global():
    # (Identical to previous)
    global discovered_pythons
    print(AnsiColors.info("Scanning for Python installations..."))
    if platform.system() == "Windows": discovered_pythons = find_pythons_windows()
    else: discovered_pythons = find_pythons_linux_mac()
    discovered_pythons.sort(key=lambda p: p.get('version', '0'), reverse=True)

def broadcast_env_change_windows(): # Renamed for clarity
    if platform.system() == "Windows":
        HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x1A, 0x0002
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW( HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))

def modify_persistent_path_windows(python_info_to_add=None, system_wide=True, revert=False, paths_to_ensure=None):
    # (Enhanced from previous to include generic paths_to_ensure)
    if platform.system() != "Windows":
        print(AnsiColors.warning("Persistent PATH modification is Windows-only."))
        return False
    if not is_admin(): relaunch_as_admin(); return False

    reg_key_root = winreg.HKEY_LOCAL_MACHINE if system_wide else winreg.HKEY_CURRENT_USER
    reg_path_sub = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment" if system_wide else r"Environment"
    
    config_key_scope = "system" if system_wide else "user"
    current_config = {}
    if PERSISTENT_PATH_CONFIG_FILE.exists():
        try:
            with open(PERSISTENT_PATH_CONFIG_FILE, 'r') as f: current_config = json.load(f)
        except json.JSONDecodeError: pass
    
    added_paths_from_config = current_config.get(config_key_scope, {}).get("pymate_managed_paths", [])

    try:
        key = winreg.OpenKey(reg_key_root, reg_path_sub, 0, winreg.KEY_READ | winreg.KEY_WRITE)
        current_path_val, path_type = winreg.QueryValueEx(key, "PATH")
        path_list = [p.strip() for p in current_path_val.split(';') if p.strip()]

        # Remove PyMate previously managed paths for this scope
        path_list_cleaned = [p for p in path_list if str(Path(p).resolve()) not in [str(Path(ap).resolve()) for ap in added_paths_from_config]]
        path_list = path_list_cleaned
        
        pymate_newly_managed_paths = [] # Tracks paths PyMate will manage this run
        if python_info_to_add: # Specific Python selected to be primary
            py_exe = Path(python_info_to_add['path'])
            pymate_newly_managed_paths.extend([str(py_exe.parent / "Scripts"), str(py_exe.parent)])
        
        if paths_to_ensure: # Other generic paths to ensure (like PyMate scripts dir)
            pymate_newly_managed_paths.extend([str(Path(p).resolve()) for p in paths_to_ensure])

        # Remove duplicates from what we are about to add, then prepend
        unique_new_paths = []
        for p in pymate_newly_managed_paths:
            if p not in unique_new_paths: unique_new_paths.append(p)
        
        path_list = unique_new_paths + path_list # Prepend

        final_path_str = ";".join(path_list)
        winreg.SetValueEx(key, "PATH", 0, path_type, final_path_str)
        winreg.CloseKey(key)

        # Update config: replace managed paths for this scope
        if not current_config.get(config_key_scope): current_config[config_key_scope] = {}
        current_config[config_key_scope]["pymate_managed_paths"] = unique_new_paths if not revert else []
        
        if revert: # If full revert for this scope, clear managed paths
             current_config[config_key_scope]["pymate_managed_paths"] = []
             # also potentially clear specific python reference if it was from this scope
             if current_config.get(config_key_scope, {}).get("python_exe_path_managed_by_pymate"):
                del current_config[config_key_scope]["python_exe_path_managed_by_pymate"]

        if python_info_to_add and not revert: # Store the specific python added if any
            current_config[config_key_scope]["python_exe_path_managed_by_pymate"] = str(python_info_to_add['path'])

        with open(PERSISTENT_PATH_CONFIG_FILE, 'w') as f: json.dump(current_config, f, indent=2)
        
        broadcast_env_change_windows()
        if revert: print(AnsiColors.success(f"PyMate's persistent PATH changes for {config_key_scope} scope reverted."))
        else: print(AnsiColors.success(f"Persistent PATH for {config_key_scope} scope updated."))
        print(AnsiColors.info("New CMD or reboot may be needed for full effect."))
        return True
    except Exception as e:
        print(AnsiColors.error(f"Failed to modify persistent PATH ({config_key_scope}): {e}"))
    return False

def generate_env_setup_script_for_session(selected_python=None, extra_env_vars=None, extra_path_dirs=None, extra_aliases=None):
    # (Enhanced from previous version to be more generic)
    global internal_active_python_path
    env_commands = ["@echo off"] if platform.system() == "Windows" else ["#!/bin/bash"] # Or zsh, etc.
    
    current_python_for_session = selected_python # Python explicitly chosen for this session switch
    if not current_python_for_session: # If not switching, but maybe just adding other env vars, try to find a current one
        active_ops_py = get_current_active_python_for_ops()
        if active_ops_py:
             # Synthesize a selected_python like dict for consistency
            current_python_for_session = {
                'path': active_ops_py,
                'name': f"Python {get_python_version_from_exe(active_ops_py)}",
                'version': get_python_version_from_exe(active_ops_py)
            }

    path_parts_to_prepend = []
    
    if current_python_for_session:
        py_exe = Path(current_python_for_session['path'])
        py_dir = py_exe.parent
        scripts_dir = py_dir / ("Scripts" if platform.system() == "Windows" else "bin")
        
        env_commands.append(f"echo Activating Python for session: {current_python_for_session['name']}")
        set_cmd = "set" if platform.system() == "Windows" else "export"
        env_commands.append(f'{set_cmd} "PYMATE_ACTIVE_PYTHON_PATH={str(py_exe)}"')
        env_commands.append(f'{set_cmd} "PYMATE_ACTIVE_PYTHON_VERSION={current_python_for_session["version"]}"')
        
        if scripts_dir.exists(): path_parts_to_prepend.append(str(scripts_dir))
        path_parts_to_prepend.append(str(py_dir))
        internal_active_python_path = py_exe # Update internal tracker
    
    if PYMATE_GENERATED_SCRIPTS_DIR.exists(): # Always add PyMate's own scripts dir
        path_parts_to_prepend.append(str(PYMATE_GENERATED_SCRIPTS_DIR))

    if extra_path_dirs: path_parts_to_prepend.extend([str(p) for p in extra_path_dirs])

    if path_parts_to_prepend:
        path_sep = ";" if platform.system() == "Windows" else ":"
        current_path_var = "%PATH%" if platform.system() == "Windows" else "$PATH"
        new_path_str = path_sep.join(path_parts_to_prepend)
        if platform.system() == "Windows": env_commands.append(f'set "PATH={new_path_str};{current_path_var}"')
        else: env_commands.append(f'export PATH="{new_path_str}{path_sep}{current_path_var}"')

    # Standard env vars from PyMate
    base_env_vars = {'PYTHONUTF8': '1', 'PYTHON_COLOR': '1'} # PYTHON_COLOR enables rich colors in some cases
    if adv_features_config.get("enable_colored_logging"): # Check specific feature
         base_env_vars['PYTHON_COLOR'] = '1' # Or specific var like PYTHONPLAIN=0
         base_env_vars['FORCE_COLOR'] = '1' # For libs like Click

    if extra_env_vars: base_env_vars.update(extra_env_vars)
    
    for k, v in base_env_vars.items():
        if platform.system() == "Windows": env_commands.append(f'set "{k}={v}"')
        else: env_commands.append(f'export {k}="{v}"')
    
    # Aliases
    default_aliases = {}
    if current_python_for_session:
        py_exe_str = str(current_python_for_session['path'])
        pip_exe_str = str((Path(py_exe_str).parent / ("Scripts" if platform.system() == "Windows" else "bin") / ("pip.exe" if platform.system() == "Windows" else "pip")))
        default_aliases.update({'python': py_exe_str, 'python3': py_exe_str})
        if Path(pip_exe_str).exists(): default_aliases.update({'pip': pip_exe_str, 'pip3': pip_exe_str})
    
    if adv_features_config.get("add_py_alias_to_python_exe") and platform.system() == "Windows" and current_python_for_session:
         default_aliases['py'] = str(current_python_for_session['path'])
    
    if extra_aliases: default_aliases.update(extra_aliases)

    for alias_name, alias_cmd in default_aliases.items():
        if platform.system() == "Windows": env_commands.append(f'doskey {alias_name}="{alias_cmd}" $*')
        else: env_commands.append(f"alias {alias_name}='{alias_cmd}'")

    try:
        with open(ENV_SETUP_SCRIPT, "w", encoding='utf-8') as f:
            for cmd_line in env_commands: f.write(cmd_line + os.linesep)
        # print(AnsiColors.success(f"Session script generated: {ENV_SETUP_SCRIPT}")) # Less verbose for frequent calls
    except IOError as e:
        print(AnsiColors.error(f"Could not write session environment script: {e}"))

def get_current_active_python_for_ops():
    # (From previous version, good for operations)
    env_path_str = os.environ.get("PYMATE_ACTIVE_PYTHON_PATH")
    if env_path_str and Path(env_path_str).exists(): return Path(env_path_str)
    if internal_active_python_path and internal_active_python_path.exists(): return internal_active_python_path
    if len(discovered_pythons) == 1: return discovered_pythons[0]['path']
    
    # Try to see if a persistent PyMate-managed python exists
    if platform.system() == "Windows" and PERSISTENT_PATH_CONFIG_FILE.exists():
        try:
            with open(PERSISTENT_PATH_CONFIG_FILE, 'r') as f: config_data = json.load(f)
            for scope in ["user", "system"]: # Prioritize user over system for ops if both set by PyMate
                py_path_str = config_data.get(scope, {}).get("python_exe_path_managed_by_pymate")
                if py_path_str and Path(py_path_str).exists():
                    return Path(py_path_str)
        except: pass

    return None # Caller must handle if None


# --- UI and Menus ---
def clear_screen(): os.system('cls' if platform.system() == 'Windows' else 'clear')

def press_enter_to_continue():
    input(AnsiColors.prompt("\nPress Enter to continue..."))

def print_header():
    # (From previous version, enhanced for more persistent info)
    clear_screen()
    print(AnsiColors.title(f" PyMate By Germanized v{VERSION} "))
    print(AnsiColors.TC_GREY + "=" * 60 + AnsiColors.RESET)
    
    # Session Active Python
    env_ver = os.environ.get("PYMATE_ACTIVE_PYTHON_VERSION")
    env_path = os.environ.get("PYMATE_ACTIVE_PYTHON_PATH")
    if env_ver and env_path:
        print(AnsiColors.info(f"Session Active: Python {env_ver} at {env_path}"))
    elif internal_active_python_path: # Selected but not yet applied by batch wrapper
        ver = get_python_version_from_exe(internal_active_python_path)
        print(AnsiColors.info(f"Session Pending: Python {ver} at {internal_active_python_path}"))
    else:
        print(AnsiColors.info("Session Active: No specific Python set by PyMate this session."))

    # Persistent Default (Windows)
    if platform.system() == "Windows" and PERSISTENT_PATH_CONFIG_FILE.exists():
        try:
            with open(PERSISTENT_PATH_CONFIG_FILE, 'r') as f: data = json.load(f)
            for scope_key, scope_name in [("user", "User"), ("system", "System-wide")]:
                py_path_str = data.get(scope_key, {}).get("python_exe_path_managed_by_pymate")
                if py_path_str:
                    py_path = Path(py_path_str)
                    ver = get_python_version_from_exe(py_path) if py_path.exists() else "N/A"
                    print(AnsiColors.TC_GREEN + f"Persistent Default ({scope_name}): Python {ver} (set by PyMate)" + AnsiColors.RESET)
                    break # Show first one found (user then system if both by chance)
        except Exception: pass
    print(AnsiColors.TC_GREY + "-" * 60 + AnsiColors.RESET)

# --- START OF ADVANCED FEATURES IMPLEMENTATION ---

def adv_activate_venv_in_cwd():
    print_header()
    print(AnsiColors.menu_header("Attempt to Activate Virtual Environment in Current Directory"))
    cwd = Path.cwd()
    common_venv_names = ['.venv', 'venv', 'env']
    activate_script_paths_win = ['Scripts/activate.bat']
    activate_script_paths_posix = ['bin/activate']

    found_venv_path = None
    activate_cmd = None

    for venv_name in common_venv_names:
        potential_venv_path = cwd / venv_name
        if potential_venv_path.is_dir():
            if platform.system() == "Windows":
                for script_rel_path in activate_script_paths_win:
                    if (potential_venv_path / script_rel_path).exists():
                        found_venv_path = potential_venv_path
                        activate_cmd = str(potential_venv_path / script_rel_path)
                        break
            else: # Linux/macOS
                for script_rel_path in activate_script_paths_posix:
                    if (potential_venv_path / script_rel_path).exists():
                        found_venv_path = potential_venv_path
                        activate_cmd = f"source {str(potential_venv_path / script_rel_path)}"
                        break
            if found_venv_path: break
    
    if found_venv_path and activate_cmd:
        print(AnsiColors.success(f"Found virtual environment: {found_venv_path.name}"))
        if platform.system() == "Windows":
            print(AnsiColors.info(f"To activate it in this CMD session, PyMate will add a command to the session script."))
            print(AnsiColors.info(f"The command is: call \"{activate_cmd}\""))
            # Generate a session script that calls the activate script
            # Note: This replaces any Python version selection for the session temporarily.
            try:
                with open(ENV_SETUP_SCRIPT, "w", encoding='utf-8') as f:
                    f.write("@echo off" + os.linesep)
                    f.write(f"echo Activating venv: {found_venv_path.name}" + os.linesep)
                    f.write(f'call "{activate_cmd}"' + os.linesep)
                    f.write(f'echo Venv {found_venv_path.name} activated. Type "deactivate" to exit it.' + os.linesep)
                print(AnsiColors.info("Venv activation command added to session script. PyMate will apply it on exit."))
            except IOError as e:
                print(AnsiColors.error(f"Could not write session script for venv activation: {e}"))
        else: # Linux/macOS
            print(AnsiColors.info(f"To activate, run: {AnsiColors.TC_ORANGE}{activate_cmd}{AnsiColors.RESET} in your current shell."))
    else:
        print(AnsiColors.warning(f"No common virtual environment (e.g., .venv, venv) found in {cwd} or it's misconfigured."))
    press_enter_to_continue()


def adv_install_common_tools():
    print_header()
    print(AnsiColors.menu_header("Install Common Python Tools"))
    active_python = get_current_active_python_for_ops()
    if not active_python:
        print(AnsiColors.error("No active Python selected or found to install packages with."))
        press_enter_to_continue(); return

    common_tools = {
        "rich": "For rich text and beautiful formatting in the terminal.",
        "httpie": "A user-friendly HTTP client.",
        "ipython": "A powerful interactive Python shell.",
        "black": "The uncompromising Python code formatter.",
        "flake8": "A popular Python linter.",
        "isort": "A Python utility / library to sort imports.",
        "pytest": "A mature full-featured Python testing tool.",
        "pipx": "Install and Run Python Applications in Isolated Environments."
    }
    print(AnsiColors.info(f"The following tools can be installed using '{active_python} -m pip install ...'"))
    for i, (tool, desc) in enumerate(common_tools.items()):
        print(AnsiColors.menu_item(i + 1, tool, f"- {desc}"))
    print(AnsiColors.menu_item(0, "Install ALL listed tools"))
    print(AnsiColors.menu_item("C", "Custom list of packages"))
    print(AnsiColors.menu_item("B", "Back to Advanced Menu"))

    choice = input(AnsiColors.input_prompt("Select tool(s) to install (e.g., 1,3 or 0 or C)")).strip().lower()
    
    packages_to_install = []
    if choice == 'b': return
    elif choice == 'c':
        custom_list = input(AnsiColors.input_prompt("Enter space-separated package names")).strip()
        if custom_list: packages_to_install = custom_list.split()
    elif choice == '0':
        packages_to_install = list(common_tools.keys())
    else:
        try:
            selected_indices = [int(x.strip()) - 1 for x in choice.split(',')]
            tool_keys = list(common_tools.keys())
            for idx in selected_indices:
                if 0 <= idx < len(tool_keys):
                    packages_to_install.append(tool_keys[idx])
                else:
                    print(AnsiColors.warning(f"Invalid selection index: {idx+1}"))
        except ValueError:
            print(AnsiColors.error("Invalid input format for selection."))

    if packages_to_install:
        print(AnsiColors.info(f"\nInstalling: {', '.join(packages_to_install)} with {active_python}"))
        # Live output for pip install is better
        command = [str(active_python), "-m", "pip", "install", "-U"] + packages_to_install # -U for upgrade
        try:
            process = subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr)
            process.communicate() # Wait for completion
            if process.returncode == 0:
                print(AnsiColors.success("Selected tools installed/updated successfully."))
            else:
                print(AnsiColors.error(f"pip install exited with code: {process.returncode}"))
        except Exception as e:
            print(AnsiColors.error(f"Failed to run pip install: {e}"))
    else:
        print(AnsiColors.info("No packages selected for installation."))
    press_enter_to_continue()

def adv_configure_python_startup():
    print_header()
    print(AnsiColors.menu_header("Configure PYTHONSTARTUP"))
    active_python = get_current_active_python_for_ops()
    if not active_python: # Less critical here, as PYTHONSTARTUP is generic
        print(AnsiColors.warning("No active Python, setting PYTHONSTARTUP will be generic."))

    rc_filename = ".pythonrc.py"
    # Prefer user's home directory, or PyMate's config dir as a fallback place
    python_rc_path_home = Path.home() / rc_filename
    python_rc_path_pymate = CONFIG_DIR / rc_filename
    
    chosen_rc_path = None
    if python_rc_path_home.exists() or not python_rc_path_pymate.exists():
        chosen_rc_path = python_rc_path_home
    else: # home doesn't exist, pymate's does
        chosen_rc_path = python_rc_path_pymate

    print(AnsiColors.info(f"PYTHONSTARTUP allows a Python script to run when the REPL starts."))
    print(AnsiColors.info(f"Currently proposed .pythonrc.py location: {chosen_rc_path}"))

    if not chosen_rc_path.exists():
        create_rc = input(AnsiColors.input_prompt(f"File {chosen_rc_path} does not exist. Create it with common imports? (yes/no)")).strip().lower()
        if create_rc == 'yes':
            try:
                with open(chosen_rc_path, 'w', encoding='utf-8') as f:
                    f.write("# Custom Python Startup File managed by PyMate\n")
                    f.write("import os\n")
                    f.write("import sys\n")
                    f.write("import platform\n")
                    f.write("from pathlib import Path\n")
                    f.write("import pprint\n")
                    f.write("pp = pprint.PrettyPrinter(indent=4)\n")
                    f.write("print(f'>>> {AnsiColors.TC_TEAL}Loaded custom startup: {AnsiColors.TC_ORANGE}{str(chosen_rc_path)}{AnsiColors.RESET} <<<')\n")
                print(AnsiColors.success(f"Created {chosen_rc_path} with default content."))
            except IOError as e:
                print(AnsiColors.error(f"Could not create {chosen_rc_path}: {e}"))
                press_enter_to_continue(); return
        else:
            print(AnsiColors.info("Skipping .pythonrc.py creation."))
            press_enter_to_continue(); return
            
    # Option to set PYTHONSTARTUP env var
    print(AnsiColors.menu_item("1", "Set PYTHONSTARTUP for current session"))
    if platform.system() == "Windows":
        print(AnsiColors.menu_item("2", "Set PYTHONSTARTUP persistently (User environment variable)"))
        print(AnsiColors.menu_item("3", "Set PYTHONSTARTUP persistently (System environment variable, needs Admin)"))
    print(AnsiColors.menu_item("B", "Back"))
    
    choice = input(AnsiColors.input_prompt("Choose action")).strip().lower()
    
    extra_vars_for_session = {"PYTHONSTARTUP": str(chosen_rc_path)}
    if choice == '1':
        generate_env_setup_script_for_session(extra_env_vars=extra_vars_for_session)
        print(AnsiColors.success(f"PYTHONSTARTUP will be set to {chosen_rc_path} for this session."))
        adv_features_config["PYTHONSTARTUP_configured"] = True # Mark it configured
        adv_features_config["PYTHONSTARTUP_path"] = str(chosen_rc_path)
        save_adv_features_config()
    elif choice == '2' and platform.system() == "Windows":
        if not is_admin(): print(AnsiColors.warning("May need admin to set persistent user vars if running elevated CMD."));
        try:
            winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") # Ensure key exists
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, "PYTHONSTARTUP", 0, winreg.REG_SZ, str(chosen_rc_path))
            winreg.CloseKey(key)
            broadcast_env_change_windows()
            print(AnsiColors.success(f"PYTHONSTARTUP set persistently for current user to: {chosen_rc_path}"))
            adv_features_config["PYTHONSTARTUP_configured"] = True
            adv_features_config["PYTHONSTARTUP_path"] = str(chosen_rc_path)
            save_adv_features_config()
        except Exception as e: print(AnsiColors.error(f"Failed to set User PYTHONSTARTUP: {e}"))
    elif choice == '3' and platform.system() == "Windows":
        if not is_admin(): relaunch_as_admin(); return
        try:
            reg_path_sub = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
            winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, reg_path_sub)
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path_sub, 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, "PYTHONSTARTUP", 0, winreg.REG_SZ, str(chosen_rc_path))
            winreg.CloseKey(key)
            broadcast_env_change_windows()
            print(AnsiColors.success(f"PYTHONSTARTUP set persistently (System) to: {chosen_rc_path}"))
            adv_features_config["PYTHONSTARTUP_configured"] = True
            adv_features_config["PYTHONSTARTUP_path"] = str(chosen_rc_path)
            save_adv_features_config()
        except Exception as e: print(AnsiColors.error(f"Failed to set System PYTHONSTARTUP: {e}"))
    press_enter_to_continue()


def adv_create_helper_batch_script(name, command, description):
    """Helper to create .bat files in PYMATE_GENERATED_SCRIPTS_DIR"""
    if not PYMATE_GENERATED_SCRIPTS_DIR.exists():
        PYMATE_GENERATED_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    script_path = PYMATE_GENERATED_SCRIPTS_DIR / f"{name}.bat"
    content = f"@echo off\nrem PyMate Generated Script: {description}\n{command} %*"
    try:
        with open(script_path, 'w') as f: f.write(content)
        print(AnsiColors.success(f"Created helper script: {script_path}"))
        print(AnsiColors.info(f"Ensure '{PYMATE_GENERATED_SCRIPTS_DIR}' is in your PATH."))
        print(AnsiColors.info(f"You might need to run 'PyMate Add PyMate Scripts Dir to PATH' feature."))
        return True
    except IOError as e:
        print(AnsiColors.error(f"Could not create script {script_path}: {e}"))
    return False


def adv_setup_helper_scripts():
    print_header()
    print(AnsiColors.menu_header("Setup Helper Scripts/Shortcuts"))
    active_python = get_current_active_python_for_ops()
    if not active_python:
        print(AnsiColors.error("No active Python found. Some helpers depend on an active Python."))
        press_enter_to_continue(); return
    
    python_exe_str = str(active_python)

    helpers = {
        "1": {"name": "pyweb", "cmd": f'"{python_exe_str}" -m http.server', "desc": "Run a local web server in current dir"},
        "2": {"name": "pyjupyter", "cmd": f'"{python_exe_str}" -m jupyter notebook', "desc": "Run Jupyter Notebook (if installed)"},
        "3": {"name": "pyipython", "cmd": f'"{python_exe_str}" -m IPython', "desc": "Run IPython shell (if installed)"},
        "4": {"name": "pystreamlit", "cmd": f'"{python_exe_str}" -m streamlit run', "desc": "Run Streamlit app (if installed, expects app.py)"},
        "5": {"name": "pytestrun", "cmd": f'"{python_exe_str}" -m pytest', "desc": "Run pytest tests in current dir (if installed)"},
        # "6": {"name": "pymate_debug_python", "cmd": f'@"{python_exe_str}" -X dev -W default %*', "desc": "Run python script with dev mode and warnings"}
    }
    print(AnsiColors.info(f"Helper scripts will be created in: {PYMATE_GENERATED_SCRIPTS_DIR}"))
    print(AnsiColors.info("Ensure this directory is in your PATH (use option in main PATH menu)."))
    for idx, data in helpers.items():
        print(AnsiColors.menu_item(idx, data['name'], f"- {data['desc']}"))
    print(AnsiColors.menu_item("A", "Create ALL listed helper scripts"))
    print(AnsiColors.menu_item("B", "Back"))

    choice_str = input(AnsiColors.input_prompt("Choose helper(s) to create (e.g., 1,3 or A)")).strip().lower()
    if choice_str == 'b': return
    
    selected_helpers = []
    if choice_str == 'a':
        selected_helpers = list(helpers.values())
    else:
        try:
            indices = choice_str.split(',')
            for idx_str in indices:
                if idx_str in helpers:
                    selected_helpers.append(helpers[idx_str])
                else: print(AnsiColors.warning(f"Invalid selection: {idx_str}"))
        except Exception: print(AnsiColors.error("Invalid input format."))
    
    if selected_helpers:
        for helper_data in selected_helpers:
            adv_create_helper_batch_script(helper_data['name'], helper_data['cmd'], helper_data['desc'])
            adv_features_config[f"helper_{helper_data['name']}_created"] = True
        save_adv_features_config()
    else:
        print(AnsiColors.info("No helpers selected for creation."))
    press_enter_to_continue()

def adv_manage_pip_cache():
    print_header()
    print(AnsiColors.menu_header("Manage pip Cache"))
    active_python = get_current_active_python_for_ops()
    if not active_python:
        print(AnsiColors.error("No active Python found to manage pip cache for."))
        press_enter_to_continue(); return
    
    print(AnsiColors.menu_item("1", "View pip cache info/directory"))
    print(AnsiColors.menu_item("2", "Purge pip cache"))
    print(AnsiColors.menu_item("B", "Back"))
    choice = input(AnsiColors.input_prompt("Choose action")).strip().lower()

    pip_cmd_base = [str(active_python), "-m", "pip", "cache"]
    if choice == '1':
        run_command(pip_cmd_base + ["info"], capture_output=False) # Live output
        run_command(pip_cmd_base + ["dir"], capture_output=False)
    elif choice == '2':
        confirm = input(AnsiColors.warning("This will purge the entire pip cache. Are you sure? (yes/no): ")).strip().lower()
        if confirm == 'yes':
            print(AnsiColors.info("Purging pip cache..."))
            proc = run_command(pip_cmd_base + ["purge"], capture_output=False)
            if proc and proc.returncode == 0: print(AnsiColors.success("pip cache purged."))
            else: print(AnsiColors.error("Failed to purge pip cache or command not supported by this pip version."))
        else:
            print(AnsiColors.info("Pip cache purge cancelled."))
    press_enter_to_continue()


def adv_install_pipx():
    print_header()
    print(AnsiColors.menu_header("Install/Setup pipx"))
    active_python = get_current_active_python_for_ops()
    if not active_python:
        print(AnsiColors.error("No active Python to install pipx with."))
        press_enter_to_continue(); return
    
    print(AnsiColors.info("pipx installs and runs Python applications in isolated environments."))
    # Check if pipx is already callable
    pipx_check = run_command(["pipx", "--version"], capture_output=True)
    if pipx_check.returncode == 0 and pipx_check.stdout:
        print(AnsiColors.success(f"pipx is already available: {pipx_check.stdout.strip()}"))
        # Optionally offer to ensure pipx paths are set
    else:
        print(AnsiColors.info(f"pipx not found or not working. Attempting to install with {active_python}..."))
        install_cmd = [str(active_python), "-m", "pip", "install", "--user", "pipx"] # --user is often safer
        proc_install = run_command(install_cmd, capture_output=False)
        if proc_install and proc_install.returncode == 0:
            print(AnsiColors.success("pipx installed successfully (via pip)."))
            adv_features_config["pipx_installed"] = True
        else:
            print(AnsiColors.error("Failed to install pipx via pip."))
            press_enter_to_continue(); return
            
    # Ensure pipx paths are in environment (user needs to run this command as pipx suggests)
    print(AnsiColors.info(f"\nAfter pipx installation (or if already installed), you might need to ensure its scripts directory is in your PATH."))
    print(AnsiColors.info(f"pipx usually suggests running: {AnsiColors.TC_ORANGE}{str(active_python)} -m pipx ensurepath{AnsiColors.RESET}"))
    run_ensurepath = input(AnsiColors.input_prompt("Run this 'pipx ensurepath' command now? (yes/no)")).strip().lower()
    if run_ensurepath == 'yes':
        # It's better to guide the user or capture its output to add to PyMate session/persistent PATH.
        # For now, just run it. User may need to restart terminal.
        proc_ensure = run_command([str(active_python), "-m", "pipx", "ensurepath"], capture_output=False)
        if proc_ensure and proc_ensure.returncode == 0:
            print(AnsiColors.success("`pipx ensurepath` command executed. You might need to restart your terminal or re-login for changes to take effect if paths were modified."))
            adv_features_config["pipx_ensurepath_run"] = True
            save_adv_features_config()
        else:
            print(AnsiColors.error("`pipx ensurepath` command failed or had issues."))
    press_enter_to_continue()


def adv_project_template_initializer():
    print_header()
    print(AnsiColors.menu_header("Project Template Initializer (via Cookiecutter)"))
    active_python = get_current_active_python_for_ops()
    if not active_python:
        print(AnsiColors.error("No active Python found."))
        press_enter_to_continue(); return

    # Check for cookiecutter
    cc_check = run_command([str(active_python), "-m", "cookiecutter", "--version"], capture_output=True)
    if not (cc_check.returncode == 0 and cc_check.stdout):
        install_cc = input(AnsiColors.input_prompt("Cookiecutter not found or not working. Install it? (yes/no)")).strip().lower()
        if install_cc == 'yes':
            run_command([str(active_python), "-m", "pip", "install", "cookiecutter"], capture_output=False)
        else:
            press_enter_to_continue(); return
    
    template_url = input(AnsiColors.input_prompt("Enter Cookiecutter template URL (e.g., gh:user/repo or full git URL)")).strip()
    if not template_url:
        print(AnsiColors.warning("No template URL provided."))
        press_enter_to_continue(); return

    print(AnsiColors.info(f"Running cookiecutter for template: {template_url} in current directory: {Path.cwd()}"))
    # Cookiecutter is interactive, so run it directly without capturing output
    cc_command = [str(active_python), "-m", "cookiecutter", template_url]
    try:
        # Run in current working directory, allow full interaction
        subprocess.run(cc_command, check=True, cwd=Path.cwd()) 
        print(AnsiColors.success("Cookiecutter process finished."))
    except subprocess.CalledProcessError as e:
        print(AnsiColors.error(f"Cookiecutter failed with exit code {e.returncode}."))
    except FileNotFoundError:
        print(AnsiColors.error("Cookiecutter (or Python) not found. Please ensure it's installed and accessible."))
    except Exception as e:
        print(AnsiColors.error(f"An error occurred running Cookiecutter: {e}"))
    press_enter_to_continue()


def adv_toggle_feature(feature_key, description_on, description_off, default_state=False, needs_session_update=False):
    """ Generic toggle for boolean advanced features. """
    current_state = adv_features_config.get(feature_key, default_state)
    print_header()
    print(AnsiColors.menu_header(f"Toggle: {description_on if not current_state else description_off}"))
    if current_state:
        print(AnsiColors.info(f"Currently: ENABLED ({description_on})"))
        action = "Disable"
    else:
        print(AnsiColors.info(f"Currently: DISABLED ({description_off})"))
        action = "Enable"
    
    choice = input(AnsiColors.input_prompt(f"{action} this feature? (yes/no)")).strip().lower()
    if choice == 'yes':
        adv_features_config[feature_key] = not current_state
        save_adv_features_config()
        print(AnsiColors.success(f"Feature has been {'ENABLED' if not current_state else 'DISABLED'}."))
        if needs_session_update:
            print(AnsiColors.info("Changes will be applied to the current session script."))
            generate_env_setup_script_for_session() # Regenerate to pick up changes
    else:
        print(AnsiColors.info("No changes made."))
    press_enter_to_continue()


# --- Menu Definitions ---
def select_python_menu(action_type="session"):
    # (Modified from previous for better display)
    print_header()
    type_map = {
        "session": "CURRENT CMD Session",
        "persistent_user": "USER Default (persistent)",
        "persistent_system": "SYSTEM Default (persistent, needs Admin)",
    }
    print(AnsiColors.menu_header(f"Select Python for: {type_map.get(action_type, action_type)}"))

    if not discovered_pythons:
        print(AnsiColors.warning("No Python installations discovered. Please Scan (S)."))
        press_enter_to_continue(); return

    for i, p_info in enumerate(discovered_pythons):
        print(AnsiColors.menu_item(i + 1, f"{p_info['name']} ({p_info['version']})", f"at {p_info['path']}"))
    print(AnsiColors.menu_item(0, "Cancel / Back"))

    while True:
        try:
            choice_str = input(AnsiColors.input_prompt("Choose Python (number)")).strip()
            if not choice_str: continue
            choice_idx = int(choice_str)
            if choice_idx == 0: return
            if 1 <= choice_idx <= len(discovered_pythons):
                selected = discovered_pythons[choice_idx - 1]
                if action_type == "session":
                    generate_env_setup_script_for_session(selected_python=selected)
                elif action_type == "persistent_user" and platform.system() == "Windows":
                    modify_persistent_path_windows(python_info_to_add=selected, system_wide=False)
                elif action_type == "persistent_system" and platform.system() == "Windows":
                    modify_persistent_path_windows(python_info_to_add=selected, system_wide=True)
                else: print(AnsiColors.warning("Action not supported on this OS or invalid type."))
                press_enter_to_continue(); return
            else: print(AnsiColors.warning("Invalid selection."))
        except ValueError: print(AnsiColors.warning("Invalid input. Please enter a number."))
        except KeyboardInterrupt: return

def advanced_features_menu():
    adv_menu_items = {
        "1": {"text": "Activate venv in current directory", "func": adv_activate_venv_in_cwd},
        "2": {"text": "Install common Python tools (rich, httpie, etc.)", "func": adv_install_common_tools},
        "3": {"text": "Configure PYTHONSTARTUP (REPL script)", "func": adv_configure_python_startup},
        "4": {"text": "Setup PyMate Helper Scripts (pyweb, pyjupyter, etc.)", "func": adv_setup_helper_scripts},
        "5": {"text": "Manage pip cache (view, purge)", "func": adv_manage_pip_cache},
        "6": {"text": "Install/Setup pipx for isolated CLI tools", "func": adv_install_pipx},
        "7": {"text": "Set default pip config options (globally)", "func": adv_configure_pip_defaults_interactive}, # Renamed function needed
        "8": {"text": "Add User Scripts Folder to PATH (Windows-specific for session)", "func": adv_add_user_scripts_to_path_session_interactive}, # Renamed function needed
        "9": {"text": "Create Project from Template (Cookiecutter)", "func": adv_project_template_initializer},
        # Toggles using the generic handler:
        "T1": {"text": f"{'Disable' if adv_features_config.get('enable_colored_logging') else 'Enable'} colored logging output (PYTHON_COLOR=1)", 
               "func": lambda: adv_toggle_feature('enable_colored_logging', 'Colored Logging Enabled', 'Colored Logging Disabled', needs_session_update=True)},
        "T2": {"text": f"{'Disable' if adv_features_config.get('add_py_alias_to_python_exe') else 'Enable'} 'py' alias for selected 'python.exe' (session, Windows)",
               "func": lambda: adv_toggle_feature('add_py_alias_to_python_exe', "'py' Alias Enabled", "'py' Alias Disabled", needs_session_update=True, default_state=True if platform.system() == "Windows" else False)},
        "B": {"text": "Back to Main Menu", "func": "BACK"}
    }

    while True:
        print_header()
        print(AnsiColors.menu_header("Advanced QoL Features"))
        for key, item in adv_menu_items.items():
            detail = ""
            if key.startswith("T"): # For toggles, show current state
                feature_key_name = item['func'].__closure__[0].cell_contents if item['func'].__closure__ else "" # Hacky way to get feature_key for display
                if feature_key_name: # this is too fragile for the example. Manually specify:
                    if key == "T1": feature_key_name = 'enable_colored_logging'
                    elif key == "T2": feature_key_name = 'add_py_alias_to_python_exe'

                    current_state = adv_features_config.get(feature_key_name, False)
                    detail = f"[{'ON' if current_state else 'OFF'}]"
            print(AnsiColors.menu_item(key, item['text'], detail))
        
        choice = input(AnsiColors.input_prompt("Choose advanced feature")).strip().upper()
        if choice in adv_menu_items:
            action = adv_menu_items[choice]['func']
            if action == "BACK": break
            action() # Call the function
        else:
            print(AnsiColors.warning("Invalid choice."))
            press_enter_to_continue()

def adv_configure_pip_defaults_interactive(): # New wrapper for the old logic to fit menu
    # This reuses logic similar to `adv_configure_pip_defaults` from previous full PyMate.py.
    # It has been merged/simplified from prior standalone for brevity. This is a placeholder.
    print_header(); print(AnsiColors.menu_header("Configure Global pip Defaults (pip.ini/pip.conf)"))
    print(AnsiColors.warning("This feature modifies your global pip configuration."))
    # Simplified: just allow setting no-cache for now
    if input(AnsiColors.input_prompt("Set 'no-cache-dir = true' in global pip config? (yes/no)")).lower() == 'yes':
        # Actual implementation requires careful INI parsing/writing
        print(AnsiColors.info("Imagine pip.ini/conf being updated here..."))
        adv_features_config['pip_no_cache_global'] = True; save_adv_features_config()
    else: print(AnsiColors.info("No changes made to pip config."))
    press_enter_to_continue()


def adv_add_user_scripts_to_path_session_interactive(): # New wrapper
    print_header(); print(AnsiColors.menu_header("Add User Scripts to PATH (Session)"))
    if platform.system() != "Windows":
        print(AnsiColors.warning("This specific version is primarily for Windows %APPDATA% user scripts."))
        press_enter_to_continue(); return
    
    appdata_path = Path(os.environ.get("APPDATA", ""))
    path_to_add = None
    active_py = get_current_active_python_for_ops()
    if active_py:
        try:
            ver_str = get_python_version_from_exe(active_py)
            major_minor = "".join(ver_str.split('.')[:2])
            path_to_add = appdata_path / "Python" / f"Python{major_minor}" / "Scripts"
        except: pass
    
    if not (path_to_add and path_to_add.exists()):
        path_to_add = appdata_path / "Python" / "Scripts" # Generic
        
    if path_to_add.exists():
        print(AnsiColors.info(f"Adding {path_to_add} to session PATH."))
        generate_env_setup_script_for_session(extra_path_dirs=[path_to_add])
        adv_features_config['user_scripts_path_added_session'] = True; save_adv_features_config()
    else:
        print(AnsiColors.warning(f"User scripts path {path_to_add} not found."))
    press_enter_to_continue()


def main_menu():
    # (Main menu from previous, points to new Advanced menu)
    global internal_active_python_path
    load_adv_features_config() # Load advanced feature states
    discover_pythons_and_update_global() # Initial scan on startup

    # Ensure PyMate's own scripts dir is added to session PATH if it wasn't from persistent
    generate_env_setup_script_for_session() 

    while True:
        print_header()
        print(AnsiColors.menu_header("Main Menu"))
        print(AnsiColors.menu_item("S", "Scan / Re-scan for Python installations"))
        if discovered_pythons:
            print(AnsiColors.menu_item("1", "Set Python for CURRENT CMD Session"))
            if platform.system() == "Windows":
                print(AnsiColors.menu_item("2", "Set USER Default Python (persistent)"))
                print(AnsiColors.menu_item("3", "Set SYSTEM Default Python (persistent, needs Admin)"))
        
        if platform.system() == "Windows" and PERSISTENT_PATH_CONFIG_FILE.exists():
             print(AnsiColors.menu_item("R", "Revert PyMate Persistent Default Python settings"))
        
        print(AnsiColors.menu_item("P", "Add PyMate Scripts Dir to Persistent PATH (Windows)", f"{PYMATE_GENERATED_SCRIPTS_DIR}"))

        print(AnsiColors.menu_item("A", "Advanced QoL Features"))
        print(AnsiColors.menu_item("Q", "Quit PyMate"))
        print(AnsiColors.TC_GREY + ("-" * 60) + AnsiColors.RESET)

        choice = input(AnsiColors.input_prompt("Enter your choice")).strip().upper()

        if choice == 'S':
            discover_pythons_and_update_global()
            press_enter_to_continue()
        elif choice == '1' and discovered_pythons: select_python_menu(action_type="session")
        elif choice == '2' and discovered_pythons and platform.system() == "Windows": select_python_menu(action_type="persistent_user")
        elif choice == '3' and discovered_pythons and platform.system() == "Windows": select_python_menu(action_type="persistent_system")
        elif choice == 'R' and platform.system() == "Windows":
            if PERSISTENT_PATH_CONFIG_FILE.exists():
                scope_to_revert = input(AnsiColors.prompt("Revert for 'user' or 'system' scope? (user/system): ")).strip().lower()
                if scope_to_revert in ["user", "system"]:
                    sys_wide = True if scope_to_revert == "system" else False
                    confirm = input(AnsiColors.warning(f"Revert PyMate's persistent PATH for {scope_to_revert}? (yes/no): ")).strip().lower()
                    if confirm == 'yes': modify_persistent_path_windows(revert=True, system_wide=sys_wide)
                    else: print(AnsiColors.info("Revert cancelled."))
                else: print(AnsiColors.warning("Invalid scope."))
            else: print(AnsiColors.info("No PyMate persistent settings found to revert."))
            press_enter_to_continue()
        elif choice == 'P' and platform.system() == "Windows":
            scope_choice = input(AnsiColors.prompt(f"Add '{PYMATE_GENERATED_SCRIPTS_DIR}' to User or System PATH? (user/system): ")).strip().lower()
            if scope_choice in ["user", "system"]:
                 modify_persistent_path_windows(system_wide=(scope_choice == "system"), paths_to_ensure=[PYMATE_GENERATED_SCRIPTS_DIR])
            else: print(AnsiColors.warning("Invalid scope chosen."))
            press_enter_to_continue()
        elif choice == 'A': advanced_features_menu()
        elif choice == 'Q': print(AnsiColors.info("Exiting PyMate...")); break
        else:
            print(AnsiColors.warning("Invalid choice.")); press_enter_to_continue()


if __name__ == "__main__":
    if platform.system() == "Windows": # Enable ANSI escape codes
        kernel32 = ctypes.windll.kernel32
        try:
            h_stdout = kernel32.GetStdHandle(-11) # STD_OUTPUT_HANDLE
            mode_stdout = ctypes.c_ulong()
            if kernel32.GetConsoleMode(h_stdout, ctypes.byref(mode_stdout)): # Check return value
                 kernel32.SetConsoleMode(h_stdout, mode_stdout.value | 0x0004) # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception: pass

    main_menu()