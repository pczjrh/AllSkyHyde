# app.py
from flask import Flask, render_template, send_from_directory, jsonify, request, redirect, url_for, Response
import os
import glob
import re
import json
import subprocess
from datetime import datetime, timedelta
import threading
import time
import shutil
import psutil
import platform
import socket

# Import requests for weather API - make it optional in case it's not installed
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: 'requests' module not found. Weather data will not be available.")
    print("Install with: pip install requests")

app = Flask(__name__)

# Configure this to match your output directory
# Note: These paths will be automatically updated by install.sh during installation
IMAGE_DIR = os.path.expanduser("~/allsky_images")
SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image_capture.py")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_config.json")  # Configuration file for persistent settings

# Global variables to track capture process
capture_interval = 300  # Default 5 minutes
is_capturing = False
capture_log = []
capture_thread = None
stop_capture_flag = False
last_capture_time = None
background_capture_enabled = False  # Track if background capture should be running

# ==================== STAY-ALIVE CONSTANTS ====================
STAY_ALIVE_PING_HOST = "8.8.8.8"  # Google DNS - reliable host to ping
STAY_ALIVE_PING_PORT = 53  # DNS port
STAY_ALIVE_CHECK_INTERVAL_SECONDS = 600  # Check connectivity every 60 seconds
STAY_ALIVE_MAX_REBOOT_ATTEMPTS = 5  # Max reboot attempts per tracking period
STAY_ALIVE_TRACKING_PERIOD_SECONDS = 3600  # 1 hour tracking period
STAY_ALIVE_CONNECTION_TIMEOUT_SECONDS = 10  # Timeout for connection test
STAY_ALIVE_RETRY_DELAY_SECONDS = 30  # Delay between reconnection attempts before reboot
STAY_ALIVE_MAX_RECONNECT_ATTEMPTS = 3  # Number of reconnection attempts before reboot

# Global variables for stay-alive feature
stay_alive_thread = None
stay_alive_stop_flag = False
stay_alive_log = []
stay_alive_reboot_attempts = []  # List of timestamps of reboot attempts
stay_alive_last_successful_ping = None
stay_alive_enabled = True  # Enable stay-alive by default
stay_alive_sudo_available = None  # None = not checked, True/False = cached result
stay_alive_sudo_password = None  # Cached sudo password from config
stay_alive_sudo_warning_logged = False  # Only log sudo warning once

# Global settings storage
app_settings = {
    "latitude": None,
    "longitude": None,
    "timezone": None,
    "dst_enabled": False,
    "openweather_api_key": None,
    "min_exposure_ms": 0.034,
    "max_exposure_ms": 30000,
    "capture_daytime": False,
    "capture_civil_twilight": False,
    "capture_nautical_twilight": False,
    "capture_astronomical_darkness": True,
    "ftp_protocol": "ftp",  # "ftp" or "sftp"
    "ftp_server": None,
    "ftp_port": 21,
    "ftp_username": None,
    "ftp_password": None,
    "ftp_remote_path": None,
    "compass_rotation": 0,
    "compass_enabled": True,
    "starmap_enabled": False,
    "starmap_magnitude_limit": 4.0,
    "starmap_show_names": True,
    "starmap_show_constellations": True,
    "starmap_opacity": 0.8,
    "starmap_color": "#FFD700",
    "starmap_rotation_adjust": 0,
    "starmap_offset_x": 0,
    "starmap_offset_y": 0,
    "starmap_scale_x": 1.0,
    "starmap_scale_y": 1.0
}

# NOTE: Configuration loading moved to after function definitions to avoid import errors


def load_config():
    """Load configuration from JSON file"""
    global app_settings, capture_interval, IMAGE_DIR, SCRIPT_PATH, background_capture_enabled

    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)

                # Load settings
                if 'settings' in config:
                    app_settings.update(config['settings'])

                # Load capture interval
                if 'capture_interval' in config:
                    capture_interval = config['capture_interval']

                # Load background capture status
                if 'background_capture_enabled' in config:
                    background_capture_enabled = config['background_capture_enabled']

                # Load exposure limits (with fallback to top-level config for backward compatibility)
                if 'min_exposure_ms' in config:
                    app_settings['min_exposure_ms'] = config['min_exposure_ms']
                if 'max_exposure_ms' in config:
                    app_settings['max_exposure_ms'] = config['max_exposure_ms']

                # Load paths (optional, can be overridden) - only if non-empty
                if config.get('image_dir'):
                    IMAGE_DIR = config['image_dir']
                if config.get('script_path'):
                    SCRIPT_PATH = config['script_path']

                print(f"Configuration loaded from {CONFIG_FILE}")
                print(f"Settings: lat={app_settings.get('latitude')}, lon={app_settings.get('longitude')}, api_key={'set' if app_settings.get('openweather_api_key') else 'not set'}")
                print(f"Exposure limits: min={app_settings.get('min_exposure_ms')}ms, max={app_settings.get('max_exposure_ms')}ms")
                return True
        else:
            print(f"Configuration file not found: {CONFIG_FILE}")
            print("Using default settings")
    except Exception as e:
        print(f"Error loading configuration: {str(e)}")
        import traceback
        traceback.print_exc()

    return False


def save_config():
    """Save configuration to JSON file"""
    global app_settings, capture_interval, IMAGE_DIR, SCRIPT_PATH, background_capture_enabled

    try:
        config = {
            "settings": app_settings,
            "capture_interval": capture_interval,
            "background_capture_enabled": background_capture_enabled,
            "image_dir": IMAGE_DIR,
            "script_path": SCRIPT_PATH,
            "min_exposure_ms": app_settings.get("min_exposure_ms", 0.034),
            "max_exposure_ms": app_settings.get("max_exposure_ms", 30000),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        print(f"Attempting to save config to: {CONFIG_FILE}")
        print(f"File exists before save: {os.path.exists(CONFIG_FILE)}")
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        print(f"Configuration saved to {CONFIG_FILE}")
        print(f"File exists after save: {os.path.exists(CONFIG_FILE)}")
        print(f"Settings: lat={app_settings.get('latitude')}, lon={app_settings.get('longitude')}, api_key={'set' if app_settings.get('openweather_api_key') else 'not set'}")
        print(f"Exposure limits: min={app_settings.get('min_exposure_ms')}ms, max={app_settings.get('max_exposure_ms')}ms")
        print(f"Compass: enabled={app_settings.get('compass_enabled')}, rotation={app_settings.get('compass_rotation')}")
        return True
    except Exception as e:
        print(f"Error saving configuration to {CONFIG_FILE}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def extract_metadata_from_filename(filename):
    """Extract metadata from the ZWO image filename"""
    metadata = {
        "timestamp": None,
        "exposure_ms": None,
        "datetime_obj": None
    }

    # Extract timestamp (format: YYYYMMDD_HHMMSS_expXXXms.png)
    timestamp_match = re.search(r'(\d{8}_\d{6})', filename)
    if timestamp_match:
        timestamp_str = timestamp_match.group(1)
        try:
            dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            metadata["timestamp"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            metadata["datetime_obj"] = dt
        except ValueError:
            pass

    # Extract exposure time (handle both milliseconds and microseconds)
    exposure_match = re.search(r'exp(\d+)ms', filename)
    if exposure_match:
        metadata["exposure_ms"] = int(exposure_match.group(1))
    else:
        # Try microseconds format
        exposure_match = re.search(r'exp(\d+)us', filename)
        if exposure_match:
            # Convert microseconds to milliseconds (as float to preserve precision)
            metadata["exposure_ms"] = float(int(exposure_match.group(1))) / 1000.0

    return metadata


def get_night_session_for_image(image_datetime):
    """
    Determine which night session an image belongs to.
    A night session runs from noon of one day to noon of the next day.
    Images taken before noon belong to the previous night, images after noon belong to that night.
    Returns a tuple: (session_start_date, session_end_date, display_label)
    """
    if image_datetime is None:
        return None, None, "Unknown Date"

    # If the image was taken before noon (12:00), it belongs to the previous night
    # If taken after noon, it belongs to tonight
    if image_datetime.hour < 12:
        # Before noon - this is the end of the previous night
        night_start = (image_datetime - timedelta(days=1)).date()
        night_end = image_datetime.date()
    else:
        # After noon - this is the start of tonight
        night_start = image_datetime.date()
        night_end = (image_datetime + timedelta(days=1)).date()

    # Format: "Night of 2024-11-13 to 2024-11-14"
    display_label = f"Night of {night_start.strftime('%Y-%m-%d')} to {night_end.strftime('%Y-%m-%d')}"

    return night_start, night_end, display_label


def get_all_images():
    """Get all ZWO images with metadata, sorted by date (newest first)"""
    # Match files with pattern: YYYYMMDD_HHMMSS_expXXXms.png or YYYYMMDD_HHMMSS_expXXXus.png
    image_files = []
    image_files.extend(glob.glob(os.path.join(IMAGE_DIR, "*_exp*ms.png")))
    image_files.extend(glob.glob(os.path.join(IMAGE_DIR, "*_exp*us.png")))

    images = []
    for img_path in image_files:
        filename = os.path.basename(img_path)
        metadata = extract_metadata_from_filename(filename)

        # Get file stats
        stats = os.stat(img_path)
        file_size = stats.st_size / (1024 * 1024)  # Convert to MB

        # Calculate night session
        night_start, night_end, night_label = get_night_session_for_image(metadata["datetime_obj"])

        images.append({
            "filename": filename,
            "path": img_path,
            "timestamp": metadata["timestamp"],
            "exposure_ms": metadata["exposure_ms"],
            "size_mb": round(file_size, 2),
            "modified": datetime.fromtimestamp(stats.st_mtime),
            "night_session_start": night_start,
            "night_session_end": night_end,
            "night_session_label": night_label
        })

    # Sort by modification time (newest first)
    images.sort(key=lambda x: x["modified"], reverse=True)
    return images


def run_single_capture(exposure_ms=None):
    """Run a single image capture"""
    global capture_log, last_capture_time

    try:
        cmd = ["python3", SCRIPT_PATH]
        if exposure_ms is not None:
            cmd.extend(["--exposure", str(exposure_ms)])

        capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Starting capture...")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Read output line by line
        for line in process.stdout:
            line = line.strip()
            if line:
                capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {line}")
                # Keep only last 100 log lines
                if len(capture_log) > 100:
                    capture_log.pop(0)

        process.wait()
        capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Capture completed (exit code: {process.returncode})")
        last_capture_time = time.time()
        
        return process.returncode == 0
    except Exception as e:
        capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {str(e)}")
        return False


def get_current_twilight_period():
    """
    Determine what twilight period we're currently in based on location and time.
    Returns: ('daytime', 'civil_twilight', 'nautical_twilight', 'astronomical_darkness', or 'unknown')
    """
    global app_settings

    # Need location to calculate
    if app_settings['latitude'] is None or app_settings['longitude'] is None:
        return 'unknown'

    try:
        import math
        now = datetime.now()
        lat = app_settings['latitude']
        lon = app_settings['longitude']

        # Calculate solar times using the same function from api_solar_info
        def calculate_solar_noon(lon):
            return 12.0 - (lon / 15.0)

        def calculate_sunrise_sunset(lat, lon, date):
            day_of_year = date.timetuple().tm_yday
            declination = 23.45 * math.sin(math.radians((360/365) * (day_of_year - 81)))
            lat_rad = math.radians(lat)
            dec_rad = math.radians(declination)
            cos_hour_angle = -math.tan(lat_rad) * math.tan(dec_rad)

            if cos_hour_angle > 1:
                return None, None
            elif cos_hour_angle < -1:
                return "00:00", "23:59"

            hour_angle = math.degrees(math.acos(cos_hour_angle))
            solar_noon = calculate_solar_noon(lon)
            sunrise_hour = solar_noon - (hour_angle / 15.0)
            sunset_hour = solar_noon + (hour_angle / 15.0)

            tz_offset = app_settings.get('timezone', 0) or 0
            if app_settings.get('dst_enabled'):
                tz_offset += 1

            sunrise_hour += tz_offset
            sunset_hour += tz_offset

            return sunrise_hour, sunset_hour

        sunrise_hour, sunset_hour = calculate_sunrise_sunset(lat, lon, now)

        if sunrise_hour is None or sunset_hour is None:
            return 'unknown'

        # Calculate twilight times
        civil_twilight_end = (sunset_hour + 0.5) % 24  # ~30 min after sunset
        nautical_twilight_end = (sunset_hour + 1.0) % 24  # ~1 hour after sunset
        astronomical_twilight_end = (sunset_hour + 1.5) % 24  # ~1.5 hours after sunset
        astronomical_twilight_begin = (sunrise_hour - 1.5) % 24  # ~1.5 hours before sunrise
        nautical_twilight_begin = (sunrise_hour - 1.0) % 24  # ~1 hour before sunrise
        civil_twilight_begin = (sunrise_hour - 0.5) % 24  # ~30 min before sunrise

        # Current time in hours
        current_hour = now.hour + now.minute / 60

        # Determine period (checking from darkest to lightest)
        # Handle cases that may cross midnight

        # Check if we're in astronomical darkness
        if astronomical_twilight_end < astronomical_twilight_begin:
            # Crosses midnight
            if current_hour >= astronomical_twilight_end or current_hour < astronomical_twilight_begin:
                return 'astronomical_darkness'
        else:
            if astronomical_twilight_end <= current_hour < astronomical_twilight_begin:
                return 'astronomical_darkness'

        # Check if we're in nautical twilight (between civil and astronomical twilight)
        if (civil_twilight_end <= current_hour < nautical_twilight_end or
            nautical_twilight_begin <= current_hour < civil_twilight_begin):
            return 'nautical_twilight'

        # Check if we're in civil twilight (just after sunset or just before sunrise)
        if (sunset_hour <= current_hour < civil_twilight_end or
            civil_twilight_begin <= current_hour < sunrise_hour):
            return 'civil_twilight'

        # Check if we're in daytime (between sunrise and sunset)
        if sunrise_hour <= current_hour < sunset_hour:
            return 'daytime'

        # If we reach here, we're in astronomical darkness (fallback for edge cases)
        return 'astronomical_darkness'

    except Exception as e:
        print(f"Error calculating twilight period: {e}")
        return 'unknown'


def should_capture_be_active():
    """
    Check if background capture should be active based on current twilight period and settings.
    Returns: (should_be_active: bool, reason: str)
    """
    global app_settings

    current_period = get_current_twilight_period()

    if current_period == 'unknown':
        # If we can't determine, default to allowing capture
        return True, "Unable to determine twilight period, allowing capture"

    # Check each period
    if current_period == 'astronomical_darkness' and app_settings.get('capture_astronomical_darkness', True):
        return True, "Astronomical darkness - capture enabled"

    if current_period == 'nautical_twilight' and app_settings.get('capture_nautical_twilight', False):
        return True, "Nautical twilight - capture enabled"

    if current_period == 'civil_twilight' and app_settings.get('capture_civil_twilight', False):
        return True, "Civil twilight - capture enabled"

    if current_period == 'daytime' and app_settings.get('capture_daytime', False):
        return True, "Daytime - capture enabled"

    return False, f"Current period ({current_period}) - capture disabled by settings"


def background_capture_loop():
    """Background thread that captures images at regular intervals"""
    global is_capturing, stop_capture_flag, capture_log, last_capture_time, background_capture_enabled

    capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Background capture started (interval: {capture_interval}s)")

    try:
        while not stop_capture_flag:
            # Check if we should capture based on twilight period settings
            should_capture, reason = should_capture_be_active()

            if should_capture:
                is_capturing = True

                # Run capture
                success = run_single_capture()

                is_capturing = False

                if success:
                    capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting {capture_interval} seconds until next capture...")
                else:
                    capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Capture failed, will retry in {capture_interval} seconds...")
            else:
                # Not in capture window
                is_capturing = False
                capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {reason}")

            # Wait for the interval (check stop flag every second)
            for _ in range(capture_interval):
                if stop_capture_flag:
                    break
                time.sleep(1)
    except Exception as e:
        capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Background capture error: {str(e)}")
        # Don't change the flag - let the user control the intent via Start/Stop buttons
        # The flag represents USER INTENT, not thread state
        # (Removed auto-correction that was causing flicker)

    capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Background capture stopped")


def start_background_capture():
    """Start the background capture thread"""
    global capture_thread, stop_capture_flag, background_capture_enabled

    if capture_thread and capture_thread.is_alive():
        return False, "Background capture already running"

    stop_capture_flag = False
    background_capture_enabled = True
    capture_thread = threading.Thread(target=background_capture_loop, daemon=True)
    capture_thread.start()

    # Save the status to config
    save_config()

    return True, "Background capture started"


def stop_background_capture():
    """Stop the background capture thread"""
    global stop_capture_flag, capture_thread, background_capture_enabled

    if not capture_thread or not capture_thread.is_alive():
        # Even if not running, update the flag and save
        background_capture_enabled = False
        save_config()
        return False, "Background capture not running"

    stop_capture_flag = True
    background_capture_enabled = False
    capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Stopping background capture...")

    # Wait for thread to finish (with timeout)
    capture_thread.join(timeout=5)

    # Save the status to config
    save_config()

    return True, "Background capture stopped"


# ==================== STAY-ALIVE FUNCTIONS ====================

def stay_alive_log_message(message):
    """Add a timestamped message to the stay-alive log"""
    global stay_alive_log
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    stay_alive_log.append(log_entry)
    # Keep only the last 100 log entries
    if len(stay_alive_log) > 100:
        stay_alive_log = stay_alive_log[-100:]
    print(f"STAY-ALIVE: {message}")


def load_sudo_password():
    """Load sudo password from config file if available."""
    global stay_alive_sudo_password

    if stay_alive_sudo_password is not None:
        return stay_alive_sudo_password

    try:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_config.json")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            password = config.get('settings', {}).get('sudo_password', '')
            if password:
                stay_alive_sudo_password = password
                return password
    except Exception as e:
        stay_alive_log_message(f"Could not load sudo password from config: {e}")

    stay_alive_sudo_password = ""  # Empty string means no password configured
    return ""


def check_sudo_available():
    """
    Check if sudo commands can be run (either passwordless or with configured password).
    Caches the result to avoid repeated checks and log spam.
    Returns True if sudo is available, False otherwise.
    """
    global stay_alive_sudo_available, stay_alive_sudo_warning_logged

    # Return cached result if already checked
    if stay_alive_sudo_available is not None:
        return stay_alive_sudo_available

    # Only check on Linux
    if platform.system() != "Linux":
        stay_alive_sudo_available = False
        return False

    # First, check if passwordless sudo works
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            stay_alive_sudo_available = True
            stay_alive_log_message("Passwordless sudo available for network commands")
            return True
    except (subprocess.TimeoutExpired, Exception):
        pass

    # Passwordless didn't work, check if we have a configured password
    password = load_sudo_password()
    if password:
        try:
            # Test sudo with password using -S flag (read from stdin)
            result = subprocess.run(
                ["sudo", "-S", "true"],
                input=password + "\n",
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                stay_alive_sudo_available = True
                stay_alive_log_message("Sudo available with configured password")
                return True
            else:
                stay_alive_log_message("WARNING: Configured sudo password is incorrect")
                stay_alive_sudo_warning_logged = True
        except subprocess.TimeoutExpired:
            stay_alive_log_message("WARNING: Sudo password test timed out")
        except Exception as e:
            stay_alive_log_message(f"WARNING: Sudo password test failed: {e}")

    # Neither method worked
    if not stay_alive_sudo_warning_logged:
        stay_alive_log_message("WARNING: Sudo not available")
        stay_alive_log_message("Network commands will be skipped")
        stay_alive_log_message("To enable, either:")
        stay_alive_log_message("  1. Set sudo_password in settings, OR")
        stay_alive_log_message("  2. Configure passwordless sudo in /etc/sudoers.d/allsky")
        stay_alive_sudo_warning_logged = True

    stay_alive_sudo_available = False
    return False


def run_sudo_command(cmd_args, description="", timeout=30):
    """
    Run a command with sudo, using password from config if needed.
    Returns (success, stdout, stderr) tuple.
    """
    if platform.system() != "Linux":
        return False, "", "Not Linux"

    if not check_sudo_available():
        return False, "", "Sudo not available"

    password = load_sudo_password()

    try:
        if password:
            # Use -S flag to read password from stdin
            full_cmd = ["sudo", "-S"] + cmd_args
            result = subprocess.run(
                full_cmd,
                input=password + "\n",
                capture_output=True,
                text=True,
                timeout=timeout
            )
        else:
            # Use -n flag for passwordless sudo
            full_cmd = ["sudo", "-n"] + cmd_args
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

        success = result.returncode == 0
        # Filter out password prompt from stderr if present
        stderr = result.stderr
        if stderr:
            stderr = '\n'.join(
                line for line in stderr.split('\n')
                if '[sudo]' not in line and 'password' not in line.lower()
            )

        return success, result.stdout, stderr

    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def check_network_connectivity():
    """
    Check if network connectivity is available by attempting to connect to a known host.
    Returns True if connected, False otherwise.
    """
    global stay_alive_last_successful_ping
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(STAY_ALIVE_CONNECTION_TIMEOUT_SECONDS)
        result = sock.connect_ex((STAY_ALIVE_PING_HOST, STAY_ALIVE_PING_PORT))
        sock.close()

        if result == 0:
            stay_alive_last_successful_ping = datetime.now()
            return True
        return False
    except socket.error as e:
        stay_alive_log_message(f"Socket error during connectivity check: {str(e)}")
        return False
    except Exception as e:
        stay_alive_log_message(f"Unexpected error during connectivity check: {str(e)}")
        return False


def get_reboot_attempts_in_tracking_period():
    """
    Get the number of reboot attempts within the current tracking period.
    Also cleans up old entries outside the tracking period.
    """
    global stay_alive_reboot_attempts

    current_time = datetime.now()
    cutoff_time = current_time - timedelta(seconds=STAY_ALIVE_TRACKING_PERIOD_SECONDS)

    # Filter out old attempts and keep only those within the tracking period
    stay_alive_reboot_attempts = [
        timestamp for timestamp in stay_alive_reboot_attempts
        if timestamp > cutoff_time
    ]

    return len(stay_alive_reboot_attempts)


def record_reboot_attempt():
    """Record a reboot attempt with the current timestamp"""
    global stay_alive_reboot_attempts
    stay_alive_reboot_attempts.append(datetime.now())


def get_time_until_next_tracking_period():
    """
    Calculate how long until the next tracking period starts.
    Returns seconds until the oldest attempt expires from the tracking window.
    """
    global stay_alive_reboot_attempts

    if not stay_alive_reboot_attempts:
        return 0

    oldest_attempt = min(stay_alive_reboot_attempts)
    time_elapsed = (datetime.now() - oldest_attempt).total_seconds()
    time_remaining = STAY_ALIVE_TRACKING_PERIOD_SECONDS - time_elapsed

    return max(0, time_remaining)


def attempt_network_reconnection():
    """
    Attempt to reconnect to the network using various methods.
    Returns True if reconnection succeeded, False otherwise.

    Strategy:
    1. First, wait briefly and check if network recovers on its own
    2. If sudo is available (passwordless or with configured password), try network restart commands
    3. Wait for network to stabilize and check again
    """
    stay_alive_log_message("Attempting network reconnection...")

    # First, wait a moment and check if the network recovers naturally
    # (This often works for brief connectivity blips)
    stay_alive_log_message("Waiting 5s for natural network recovery...")
    time.sleep(5)

    if check_network_connectivity():
        stay_alive_log_message("Network recovered naturally!")
        return True

    # Check if we can run sudo commands (passwordless or with password)
    sudo_available = check_sudo_available()

    if platform.system() == "Linux":
        if sudo_available:
            # Linux-specific network restart commands
            # Commands are specified without sudo prefix - run_sudo_command adds it
            reconnection_commands = [
                # Try dhclient first as it's less disruptive
                (["dhclient", "-r"], "Release DHCP lease"),
                (["dhclient"], "Renew DHCP lease"),
                # Try bringing WiFi interface down and up
                (["ip", "link", "set", "wlan0", "down"], "Disable WiFi"),
                (["ip", "link", "set", "wlan0", "up"], "Enable WiFi"),
                # Try ethernet as well
                (["ip", "link", "set", "eth0", "down"], "Disable Ethernet"),
                (["ip", "link", "set", "eth0", "up"], "Enable Ethernet"),
                # Last resort: restart NetworkManager
                (["systemctl", "restart", "NetworkManager"], "Restart NetworkManager"),
            ]

            for cmd_args, description in reconnection_commands:
                stay_alive_log_message(f"{description}...")
                success, stdout, stderr = run_sudo_command(cmd_args, description, timeout=30)

                if success:
                    stay_alive_log_message(f"  Success")
                else:
                    # Don't log full error for non-existent interfaces (common)
                    if "Cannot find device" in stderr or "does not exist" in stderr:
                        stay_alive_log_message(f"  Skipped (interface not found)")
                    elif stderr:
                        stay_alive_log_message(f"  Failed: {stderr.strip()[:100]}")
                    else:
                        stay_alive_log_message(f"  Failed")

                # Brief pause between commands
                time.sleep(1)

                # Check if network came back after each command
                if check_network_connectivity():
                    stay_alive_log_message("Network reconnection successful!")
                    return True
        else:
            stay_alive_log_message("Sudo not available - skipping network commands")
            stay_alive_log_message("Set sudo_password in settings or configure passwordless sudo")

    elif platform.system() == "Windows":
        # Windows commands don't need sudo
        reconnection_commands = [
            (["ipconfig", "/release"], "Release IP"),
            (["ipconfig", "/renew"], "Renew IP"),
        ]

        for cmd, description in reconnection_commands:
            try:
                stay_alive_log_message(f"{description}...")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    stay_alive_log_message(f"  Success")
                else:
                    stay_alive_log_message(f"  Failed: {result.stderr.strip()[:100]}")
            except subprocess.TimeoutExpired:
                stay_alive_log_message(f"  Timeout")
            except Exception as e:
                stay_alive_log_message(f"  Error: {str(e)[:50]}")

            time.sleep(1)

    # Final wait for network to stabilize
    stay_alive_log_message("Waiting 10s for network to stabilize...")
    time.sleep(10)

    # Final connectivity check
    if check_network_connectivity():
        stay_alive_log_message("Network reconnection successful!")
        return True

    stay_alive_log_message("Network reconnection failed - may need system reboot")
    return False


def perform_system_reboot():
    """
    Perform a system reboot to attempt to restore network connectivity.
    Records the reboot attempt before initiating.
    Returns True if reboot was initiated, False if it couldn't be performed.
    """
    record_reboot_attempt()
    stay_alive_log_message("INITIATING SYSTEM REBOOT...")

    # Save any configuration before reboot
    try:
        save_config()
    except Exception as e:
        stay_alive_log_message(f"Failed to save config before reboot: {str(e)}")

    # Give a moment for logs to be written
    time.sleep(2)

    try:
        if platform.system() == "Linux":
            # Check if we can use sudo (passwordless or with password)
            if not check_sudo_available():
                stay_alive_log_message("ERROR: Cannot reboot - sudo not available")
                stay_alive_log_message("Set sudo_password in settings or configure passwordless sudo")
                return False

            # Use the run_sudo_command helper which handles password if needed
            success, stdout, stderr = run_sudo_command(["reboot"], "System reboot", timeout=10)
            if not success:
                stay_alive_log_message(f"Reboot command failed: {stderr.strip()}")
                return False
            return True

        elif platform.system() == "Windows":
            # Use shutdown command on Windows (doesn't need sudo)
            subprocess.run(["shutdown", "/r", "/t", "5", "/c", "AllSky stay-alive reboot"], check=True)
            return True
        else:
            stay_alive_log_message(f"Unsupported platform for reboot: {platform.system()}")
            return False
    except Exception as e:
        stay_alive_log_message(f"Failed to initiate reboot: {str(e)}")
        return False


def reset_stay_alive_tracking():
    """Reset all stay-alive tracking data after successful reconnection"""
    global stay_alive_reboot_attempts, stay_alive_last_successful_ping
    stay_alive_reboot_attempts = []
    stay_alive_last_successful_ping = datetime.now()
    stay_alive_log_message("Stay-alive tracking reset after successful connection")


def stay_alive_monitor_loop():
    """
    Background thread that monitors network connectivity and takes action if connection is lost.
    """
    global stay_alive_stop_flag, stay_alive_last_successful_ping

    stay_alive_log_message("Stay-alive monitor started")
    stay_alive_log_message(f"Ping host: {STAY_ALIVE_PING_HOST}:{STAY_ALIVE_PING_PORT}")
    stay_alive_log_message(f"Check interval: {STAY_ALIVE_CHECK_INTERVAL_SECONDS}s")
    stay_alive_log_message(f"Max reboots per period: {STAY_ALIVE_MAX_REBOOT_ATTEMPTS}")
    stay_alive_log_message(f"Tracking period: {STAY_ALIVE_TRACKING_PERIOD_SECONDS}s ({STAY_ALIVE_TRACKING_PERIOD_SECONDS/3600:.1f} hours)")

    waiting_for_next_period = False

    while not stay_alive_stop_flag:
        try:
            # Check if we're in a waiting period due to max reboots
            reboot_count = get_reboot_attempts_in_tracking_period()

            if reboot_count >= STAY_ALIVE_MAX_REBOOT_ATTEMPTS:
                if not waiting_for_next_period:
                    time_remaining = get_time_until_next_tracking_period()
                    stay_alive_log_message(
                        f"Max reboot attempts ({STAY_ALIVE_MAX_REBOOT_ATTEMPTS}) reached. "
                        f"Waiting {time_remaining/60:.1f} minutes until next attempt window."
                    )
                    waiting_for_next_period = True

                # Still check connectivity - we might recover naturally
                if check_network_connectivity():
                    stay_alive_log_message("Connection restored during waiting period!")
                    reset_stay_alive_tracking()
                    waiting_for_next_period = False

                # Sleep and continue checking
                for _ in range(STAY_ALIVE_CHECK_INTERVAL_SECONDS):
                    if stay_alive_stop_flag:
                        break
                    time.sleep(1)
                continue

            waiting_for_next_period = False

            # Check network connectivity
            if check_network_connectivity():
                # Connection is good
                pass
            else:
                # Connection lost - attempt recovery
                stay_alive_log_message("Network connectivity lost!")
                stay_alive_log_message(f"Reboot attempts in current period: {reboot_count}/{STAY_ALIVE_MAX_REBOOT_ATTEMPTS}")

                # Try reconnection attempts first
                reconnection_successful = False
                for attempt in range(STAY_ALIVE_MAX_RECONNECT_ATTEMPTS):
                    stay_alive_log_message(f"Reconnection attempt {attempt + 1}/{STAY_ALIVE_MAX_RECONNECT_ATTEMPTS}")

                    if attempt_network_reconnection():
                        reconnection_successful = True
                        stay_alive_log_message("Network recovered without reboot!")
                        reset_stay_alive_tracking()
                        break

                    # Wait before next attempt
                    stay_alive_log_message(f"Waiting {STAY_ALIVE_RETRY_DELAY_SECONDS}s before next attempt...")
                    for _ in range(STAY_ALIVE_RETRY_DELAY_SECONDS):
                        if stay_alive_stop_flag:
                            break
                        time.sleep(1)

                    if stay_alive_stop_flag:
                        break

                # If reconnection failed, consider reboot
                if not reconnection_successful and not stay_alive_stop_flag:
                    if reboot_count < STAY_ALIVE_MAX_REBOOT_ATTEMPTS:
                        stay_alive_log_message(
                            f"All reconnection attempts failed. Initiating reboot "
                            f"(attempt {reboot_count + 1}/{STAY_ALIVE_MAX_REBOOT_ATTEMPTS})"
                        )
                        perform_system_reboot()
                        # If we get here, reboot failed
                        stay_alive_log_message("Reboot command may have failed")
                    else:
                        stay_alive_log_message("Max reboot attempts reached, waiting for next period")

            # Wait for next check interval
            for _ in range(STAY_ALIVE_CHECK_INTERVAL_SECONDS):
                if stay_alive_stop_flag:
                    break
                time.sleep(1)

        except Exception as e:
            stay_alive_log_message(f"Error in stay-alive monitor: {str(e)}")
            import traceback
            traceback.print_exc()
            # Wait a bit before continuing
            time.sleep(10)

    stay_alive_log_message("Stay-alive monitor stopped")


def start_stay_alive_monitor():
    """Start the stay-alive monitor thread"""
    global stay_alive_thread, stay_alive_stop_flag, stay_alive_enabled

    if stay_alive_thread and stay_alive_thread.is_alive():
        return False, "Stay-alive monitor already running"

    stay_alive_stop_flag = False
    stay_alive_enabled = True
    stay_alive_thread = threading.Thread(target=stay_alive_monitor_loop, daemon=True)
    stay_alive_thread.start()

    return True, "Stay-alive monitor started"


def stop_stay_alive_monitor():
    """Stop the stay-alive monitor thread"""
    global stay_alive_stop_flag, stay_alive_thread, stay_alive_enabled

    if not stay_alive_thread or not stay_alive_thread.is_alive():
        stay_alive_enabled = False
        return False, "Stay-alive monitor not running"

    stay_alive_stop_flag = True
    stay_alive_enabled = False
    stay_alive_log_message("Stopping stay-alive monitor...")

    # Wait for thread to finish (with timeout)
    stay_alive_thread.join(timeout=5)

    return True, "Stay-alive monitor stopped"


def get_stay_alive_status():
    """Get the current status of the stay-alive system"""
    reboot_count = get_reboot_attempts_in_tracking_period()
    time_until_next = get_time_until_next_tracking_period()

    return {
        "enabled": stay_alive_enabled,
        "running": stay_alive_thread is not None and stay_alive_thread.is_alive(),
        "last_successful_ping": stay_alive_last_successful_ping.isoformat() if stay_alive_last_successful_ping else None,
        "reboot_attempts_in_period": reboot_count,
        "max_reboot_attempts": STAY_ALIVE_MAX_REBOOT_ATTEMPTS,
        "tracking_period_seconds": STAY_ALIVE_TRACKING_PERIOD_SECONDS,
        "time_until_next_period_seconds": time_until_next,
        "check_interval_seconds": STAY_ALIVE_CHECK_INTERVAL_SECONDS,
        "ping_host": f"{STAY_ALIVE_PING_HOST}:{STAY_ALIVE_PING_PORT}",
        "log": stay_alive_log[-20:]  # Last 20 log entries
    }


@app.route('/')
def index():
    """Main page showing the latest image with zoom/pan functionality"""
    images = get_all_images()
    latest_image = images[0] if images else None

    # Add the timestamp of the last capture for the countdown
    last_capture_timestamp = None
    if latest_image and 'timestamp' in latest_image:
        try:
            dt = datetime.strptime(latest_image['timestamp'], '%Y-%m-%d %H:%M:%S')
            last_capture_timestamp = int(dt.timestamp())
        except (ValueError, TypeError):
            pass

    # NOTE: Removed run_capture_script() call from here!

    # Get compass and starmap settings - read fresh from config file to handle multi-worker scenarios
    compass_rotation = 0
    compass_enabled = True
    starmap_enabled = False
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                compass_rotation = config.get('settings', {}).get('compass_rotation', 0)
                compass_enabled = config.get('settings', {}).get('compass_enabled', True)
                starmap_enabled = config.get('settings', {}).get('starmap_enabled', False)
    except Exception as e:
        print(f"Error reading settings: {e}")
    print(f"Index page - Compass: enabled={compass_enabled}, rotation={compass_rotation}, Starmap: enabled={starmap_enabled}")

    response = app.make_response(render_template('index.html',
                           latest_image=latest_image,
                           capture_interval=capture_interval,
                           last_capture_timestamp=last_capture_timestamp,
                           background_running=background_capture_enabled,
                           compass_rotation=compass_rotation,
                           compass_enabled=compass_enabled,
                           starmap_enabled=starmap_enabled))

    # Add cache control headers to prevent browser caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response


@app.route('/api/last_capture_time')
def last_capture_time_api():
    """API endpoint to get the last capture time"""
    try:
        image_files = get_all_images()
        
        if not image_files:
            return jsonify({"timestamp": 0})
        
        latest_image = image_files[0]
        
        if latest_image['timestamp']:
            try:
                dt = datetime.strptime(latest_image['timestamp'], '%Y-%m-%d %H:%M:%S')
                unix_timestamp = int(dt.timestamp())
                return jsonify({"timestamp": unix_timestamp})
            except (ValueError, TypeError):
                pass
        
        # Fallback to file modification time
        unix_timestamp = int(latest_image['modified'].timestamp())
        return jsonify({"timestamp": unix_timestamp})
    
    except Exception as e:
        app.logger.error(f"Error getting last capture time: {str(e)}")
        return jsonify({"timestamp": 0, "error": str(e)})


@app.route('/gallery')
def gallery():
    """Gallery page showing all captured images"""
    images = get_all_images()
    return render_template('gallery.html', images=images)


@app.route('/image/<path:filename>')
def image_detail(filename):
    """Detail page for a specific image"""
    global app_settings

    image_path = os.path.join(IMAGE_DIR, filename)

    if not os.path.exists(image_path):
        return redirect(url_for('index'))

    metadata = extract_metadata_from_filename(filename)

    # Get file stats
    stats = os.stat(image_path)
    file_size = stats.st_size / (1024 * 1024)  # Convert to MB

    # Get the datetime object for starmap calculation
    # If we have a datetime from the filename, use it; otherwise use file modified time
    image_datetime = metadata.get("datetime_obj")
    if image_datetime:
        # Convert to ISO format for JavaScript
        image_timestamp_iso = image_datetime.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        # Fallback to file modified time
        image_timestamp_iso = datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%dT%H:%M:%S")

    image_data = {
        "filename": filename,
        "timestamp": metadata["timestamp"],
        "exposure_ms": metadata["exposure_ms"],
        "size_mb": round(file_size, 2),
        "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    }

    # Get starmap settings for the overlay
    starmap_settings = {
        "show_names": app_settings.get('starmap_show_names', True),
        "show_constellations": app_settings.get('starmap_show_constellations', True),
        "opacity": app_settings.get('starmap_opacity', 0.8),
        "color": app_settings.get('starmap_color', '#FFD700'),
        "magnitude_limit": app_settings.get('starmap_magnitude_limit', 4.0),
        "rotation_adjust": app_settings.get('starmap_rotation_adjust', 0),
        "offset_x": app_settings.get('starmap_offset_x', 0),
        "offset_y": app_settings.get('starmap_offset_y', 0),
        "scale_x": app_settings.get('starmap_scale_x', 1.0),
        "scale_y": app_settings.get('starmap_scale_y', 1.0)
    }

    return render_template('image_detail.html',
                           image=image_data,
                           image_timestamp_iso=image_timestamp_iso,
                           starmap_settings=starmap_settings)


@app.route('/control')
def control_panel():
    """Control panel for manual image capture"""
    return render_template('control.html',
                           is_capturing=is_capturing,
                           capture_log=capture_log,
                           background_running=background_capture_enabled,
                           capture_interval=capture_interval)


@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve the images from the IMAGE_DIR directory"""
    response = send_from_directory(IMAGE_DIR, filename)
    # Add cache control headers to prevent browser caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/api/latest_image_preview')
def api_latest_image_preview():
    """API endpoint optimized for ESP32 displays - serves latest image as resized JPEG"""
    global background_capture_enabled

    try:
        from PIL import Image
        import io

        # Check if background capture is enabled
        if not background_capture_enabled:
            return jsonify({"status": "error", "message": "Background capture disabled", "capturing": False}), 503

        # Get the latest image
        images = get_all_images()
        if not images:
            return jsonify({"status": "error", "message": "No images available", "capturing": background_capture_enabled}), 404

        latest_image = images[0]
        image_path = latest_image['path']

        # Get optional parameters for size (default to 320x480 for ESP32)
        width = request.args.get('width', 320, type=int)
        height = request.args.get('height', 480, type=int)
        quality = request.args.get('quality', 85, type=int)  # JPEG quality 1-100
        rotate = request.args.get('rotate', 0, type=int)  # Rotation in degrees (0, 90, 180, 270)

        # Open and process the image
        img = Image.open(image_path)

        # Convert grayscale to RGB for better compatibility
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Rotate image if requested (before resizing)
        if rotate == 90:
            img = img.rotate(-90, expand=True)
        elif rotate == 180:
            img = img.rotate(180, expand=True)
        elif rotate == 270:
            img = img.rotate(90, expand=True)

        # Resize maintaining aspect ratio
        img.thumbnail((width, height), Image.Resampling.LANCZOS)

        # Create a new image with the exact dimensions (add black bars if needed)
        final_img = Image.new('RGB', (width, height), (0, 0, 0))
        # Center the thumbnail
        offset_x = (width - img.width) // 2
        offset_y = (height - img.height) // 2
        final_img.paste(img, (offset_x, offset_y))

        # Convert to JPEG in memory
        img_io = io.BytesIO()
        final_img.save(img_io, 'JPEG', quality=quality, optimize=True)
        img_io.seek(0)

        # Return with appropriate headers
        response = Response(img_io.getvalue(), mimetype='image/jpeg')
        response.headers['X-Image-Filename'] = latest_image['filename']
        response.headers['X-Image-Timestamp'] = latest_image['timestamp']
        response.headers['X-Image-Exposure-Ms'] = str(latest_image['exposure_ms'])
        response.headers['X-Capturing'] = 'true' if background_capture_enabled else 'false'

        return response

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/weather')
def api_weather():
    """API endpoint to get current weather data for ESP32"""
    try:
        # Get weather data using the existing function
        weather_data = {
            "description": "Not available",
            "icon": "🌤",
            "clouds": None,
            "rain": None,
            "temperature": None,
            "humidity": None,
            "pressure": None,
            "wind_speed": None,
            "wind_gust": None
        }

        if REQUESTS_AVAILABLE and app_settings.get('openweather_api_key') and app_settings['openweather_api_key'].strip():
            try:
                api_key = app_settings['openweather_api_key']
                lat = app_settings.get('latitude', 0)
                lon = app_settings.get('longitude', 0)

                url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
                response = requests.get(url, timeout=10)

                if response.status_code == 200:
                    weather_json = response.json()

                    weather_data["description"] = weather_json.get("weather", [{}])[0].get("description", "Unknown").capitalize()
                    weather_data["temperature"] = weather_json.get("main", {}).get("temp")
                    weather_data["humidity"] = weather_json.get("main", {}).get("humidity")
                    weather_data["pressure"] = weather_json.get("main", {}).get("pressure")
                    weather_data["clouds"] = weather_json.get("clouds", {}).get("all")
                    weather_data["rain"] = weather_json.get("rain", {}).get("1h", 0)
                    weather_data["wind_speed"] = weather_json.get("wind", {}).get("speed")
                    weather_data["wind_gust"] = weather_json.get("wind", {}).get("gust")

                    # Get weather icon code
                    icon_code = weather_json.get("weather", [{}])[0].get("icon", "01d")
                    weather_data["icon_code"] = icon_code

            except Exception as e:
                print(f"Error fetching weather: {e}")

        return jsonify(weather_data)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/images')
def api_images():
    """API endpoint to get all images as JSON"""
    images = get_all_images()
    # Convert datetime objects to strings for JSON serialization
    for img in images:
        img["modified"] = img["modified"].strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(images)


@app.route('/api/capture', methods=['POST'])
def api_capture():
    """API endpoint to trigger a single manual image capture"""
    global is_capturing
    
    if is_capturing:
        return jsonify({"status": "error", "message": "Capture already in progress"})

    exposure_ms = request.form.get('exposure_ms')
    if exposure_ms:
        try:
            exposure_ms = int(exposure_ms)
        except ValueError:
            return jsonify({"status": "error", "message": "Exposure must be a number"})
    else:
        exposure_ms = None

    # Run capture in background thread for manual capture
    def manual_capture():
        global is_capturing
        is_capturing = True
        run_single_capture(exposure_ms)
        is_capturing = False
    
    thread = threading.Thread(target=manual_capture, daemon=True)
    thread.start()
    
    return jsonify({"status": "success", "message": "Manual capture started"})


@app.route('/api/capture_status')
def api_capture_status():
    """API endpoint to get the current capture status"""
    global background_capture_enabled, capture_thread

    # Return the status based on the persistent flag
    # The flag represents the USER'S INTENT, not the thread state
    # If the thread crashes, the flag stays true so we can restart it
    return jsonify({
        "is_capturing": is_capturing,
        "log": capture_log,
        "background_running": background_capture_enabled,
        "capture_interval": capture_interval,
        "thread_alive": capture_thread and capture_thread.is_alive()  # For debugging
    })


@app.route('/api/download_logs')
def api_download_logs():
    """API endpoint to download capture logs as a text file"""
    global capture_log

    # Create log content with timestamp
    log_content = f"AllSkyHyde Capture Logs\n"
    log_content += f"Downloaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    log_content += "="*60 + "\n\n"

    if capture_log:
        for line in capture_log:
            log_content += line + "\n"
    else:
        log_content += "No logs available\n"

    # Return as downloadable text file
    return Response(
        log_content,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment;filename=allskyhyde_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"}
    )


@app.route('/api/background_capture/start', methods=['POST'])
def api_start_background():
    """Start background capture loop"""
    success, message = start_background_capture()
    return jsonify({"status": "success" if success else "error", "message": message})


@app.route('/api/background_capture/stop', methods=['POST'])
def api_stop_background():
    """Stop background capture loop"""
    success, message = stop_background_capture()
    return jsonify({"status": "success" if success else "error", "message": message})


@app.route('/api/capture_interval', methods=['POST'])
def api_set_interval():
    """Update the capture interval"""
    global capture_interval, background_capture_enabled

    try:
        new_interval = int(request.form.get('interval', 300))
        if new_interval < 30:
            return jsonify({"status": "error", "message": "Interval must be at least 30 seconds"})

        capture_interval = new_interval

        # Save configuration to file
        save_config()

        # If background capture is enabled, restart it with new interval
        if background_capture_enabled:
            stop_background_capture()
            time.sleep(1)
            start_background_capture()
            message = f"Capture interval updated to {capture_interval} seconds and restarted"
        else:
            message = f"Capture interval updated to {capture_interval} seconds"

        return jsonify({"status": "success", "message": message})
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid interval value"})


@app.route('/api/delete_images', methods=['POST'])
def api_delete_images():
    """Delete images for selected days, preserving the latest image"""
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON data"}), 400

        days_to_delete = data.get('days', [])

        if not days_to_delete:
            return jsonify({"status": "error", "message": "No days specified for deletion"}), 400

        # Get all images
        all_images = get_all_images()

        if not all_images:
            return jsonify({"status": "error", "message": "No images found"})

        # Identify the latest image (first in the sorted list)
        latest_image_filename = all_images[0]['filename']

        # Collect images to delete
        images_to_delete = []
        deleted_days = []

        for image in all_images:
            # Skip the latest image
            if image['filename'] == latest_image_filename:
                continue

            # Get the night session label for this image (e.g., "Night of 2026-01-13 to 2026-01-14")
            image_night_label = image.get('night_session_label', 'Unknown Date')

            # If this image's night session is in the deletion list, mark it for deletion
            if image_night_label in days_to_delete:
                images_to_delete.append(image)
                if image_night_label not in deleted_days:
                    deleted_days.append(image_night_label)

        # Delete the images
        deleted_count = 0
        failed_deletions = []

        for image in images_to_delete:
            try:
                if os.path.exists(image['path']):
                    os.remove(image['path'])
                    deleted_count += 1
            except Exception as e:
                failed_deletions.append(f"{image['filename']}: {str(e)}")

        # Prepare response
        if failed_deletions:
            message = f"Deleted {deleted_count} images, but {len(failed_deletions)} failed: {', '.join(failed_deletions)}"
            status = "partial"
        else:
            message = f"Successfully deleted {deleted_count} images from {len(deleted_days)} day(s)"
            status = "success"

        return jsonify({
            "status": status,
            "message": message,
            "deleted_count": deleted_count,
            "deleted_days": deleted_days,
            "latest_image_preserved": latest_image_filename
        })

    except Exception as e:
        app.logger.error(f"Error deleting images: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500


@app.route('/system_status')
def system_status():
    # Get disk space information
    total, used, free = shutil.disk_usage("/")
    disk_total_gb = total // (2 ** 30)
    disk_used_gb = used // (2 ** 30)
    disk_free_gb = free // (2 ** 30)
    disk_percent_used = (used / total) * 100

    # Get CPU temperature (implementation depends on platform)
    cpu_temp = get_cpu_temperature()

    # Get CPU usage
    cpu_usage = psutil.cpu_percent(interval=1)

    # Get memory usage
    memory = psutil.virtual_memory()
    memory_total_gb = memory.total // (2 ** 30)
    memory_used_gb = memory.used // (2 ** 30)
    memory_percent = memory.percent

    # Get system uptime
    uptime_seconds = int(time.time() - psutil.boot_time())
    uptime_days = uptime_seconds // (60 * 60 * 24)
    uptime_hours = (uptime_seconds % (60 * 60 * 24)) // (60 * 60)
    uptime_minutes = (uptime_seconds % (60 * 60)) // 60

    # Get system information
    system_info = {
        "platform": platform.platform(),
        "hostname": platform.node(),
        "python_version": platform.python_version(),
        "processor": platform.processor()
    }

    # Get image directory size
    image_dir_size = get_directory_size(IMAGE_DIR) // (2 ** 20)  # Size in MB
    image_count = len(os.listdir(IMAGE_DIR))

    return render_template('system_status.html',
                           disk_total=disk_total_gb,
                           disk_used=disk_used_gb,
                           disk_free=disk_free_gb,
                           disk_percent=disk_percent_used,
                           cpu_temp=cpu_temp,
                           cpu_usage=cpu_usage,
                           memory_total=memory_total_gb,
                           memory_used=memory_used_gb,
                           memory_percent=memory_percent,
                           uptime_days=uptime_days,
                           uptime_hours=uptime_hours,
                           uptime_minutes=uptime_minutes,
                           system_info=system_info,
                           image_dir_size=image_dir_size,
                           image_count=image_count)


@app.route('/api/system/restart', methods=['POST'])
def system_restart():
    """Restart the system."""
    try:
        import os
        print("="*80)
        print("SYSTEM RESTART REQUESTED")
        print("="*80)
        app.logger.info("="*80)
        app.logger.info("SYSTEM RESTART REQUESTED")

        # Log environment info
        print(f"Platform: {platform.system()}")
        print(f"User: {os.getenv('USER', 'unknown')}")
        print(f"PATH: {os.getenv('PATH', 'not set')}")
        app.logger.info(f"Platform: {platform.system()}")
        app.logger.info(f"User: {os.getenv('USER', 'unknown')}")

        # Stop background capture before restart
        print("Stopping background capture...")
        app.logger.info("Stopping background capture...")
        stop_background_capture()
        print("Background capture stopped")
        app.logger.info("Background capture stopped")

        # Platform-specific restart commands
        if platform.system() == "Linux":
            # Execute reboot command directly (passwordless sudo configured in sudoers)
            print("Executing: /usr/bin/sudo /usr/sbin/reboot")
            app.logger.info("Executing: /usr/bin/sudo /usr/sbin/reboot")

            result = subprocess.run("/usr/bin/sudo /usr/sbin/reboot", shell=True,
                                   capture_output=True, text=True, timeout=5)

            print(f"Reboot command exit code: {result.returncode}")
            print(f"Reboot stdout: {result.stdout}")
            print(f"Reboot stderr: {result.stderr}")
            app.logger.info(f"Reboot command exit code: {result.returncode}")
            app.logger.info(f"Reboot stdout: {result.stdout}")
            app.logger.info(f"Reboot stderr: {result.stderr}")

            # Exit code -15 (SIGTERM) is expected when system is shutting down
            if result.returncode != 0 and result.returncode != -15:
                error_msg = f"Reboot command failed with exit code {result.returncode}. stderr: {result.stderr}"
                print(error_msg)
                app.logger.error(error_msg)
                return jsonify({"status": "error", "message": error_msg}), 500

            print("Reboot command executed successfully (system is rebooting)")
            app.logger.info("Reboot command executed successfully (system is rebooting)")
            print("="*80)

        elif platform.system() == "Windows":
            subprocess.Popen(["shutdown", "/r", "/t", "5"])
        else:
            return jsonify({"status": "error", "message": "Unsupported platform"}), 400

        return jsonify({"status": "success", "message": "System restart command executed successfully. System should restart shortly."})
    except subprocess.TimeoutExpired:
        error_msg = "Reboot command timed out (this might be normal as system is shutting down)"
        print(error_msg)
        app.logger.warning(error_msg)
        return jsonify({"status": "success", "message": error_msg})
    except Exception as e:
        error_msg = f"Error restarting system: {str(e)}"
        print(error_msg)
        app.logger.error(error_msg)
        import traceback
        traceback.print_exc()
        app.logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/system/shutdown', methods=['POST'])
def system_shutdown():
    """Shutdown the system."""
    try:
        import os
        print("="*80)
        print("SYSTEM SHUTDOWN REQUESTED")
        print("="*80)
        app.logger.info("="*80)
        app.logger.info("SYSTEM SHUTDOWN REQUESTED")

        # Log environment info
        print(f"Platform: {platform.system()}")
        print(f"User: {os.getenv('USER', 'unknown')}")
        print(f"PATH: {os.getenv('PATH', 'not set')}")
        app.logger.info(f"Platform: {platform.system()}")
        app.logger.info(f"User: {os.getenv('USER', 'unknown')}")

        # Stop background capture before shutdown
        print("Stopping background capture...")
        app.logger.info("Stopping background capture...")
        stop_background_capture()
        print("Background capture stopped")
        app.logger.info("Background capture stopped")

        # Platform-specific shutdown commands
        if platform.system() == "Linux":
            # Execute poweroff command directly (passwordless sudo configured in sudoers)
            print("Executing: /usr/bin/sudo /usr/sbin/poweroff")
            app.logger.info("Executing: /usr/bin/sudo /usr/sbin/poweroff")

            result = subprocess.run("/usr/bin/sudo /usr/sbin/poweroff", shell=True,
                                   capture_output=True, text=True, timeout=5)

            print(f"Poweroff command exit code: {result.returncode}")
            print(f"Poweroff stdout: {result.stdout}")
            print(f"Poweroff stderr: {result.stderr}")
            app.logger.info(f"Poweroff command exit code: {result.returncode}")
            app.logger.info(f"Poweroff stdout: {result.stdout}")
            app.logger.info(f"Poweroff stderr: {result.stderr}")

            # Exit code -15 (SIGTERM) is expected when system is shutting down
            if result.returncode != 0 and result.returncode != -15:
                error_msg = f"Poweroff command failed with exit code {result.returncode}. stderr: {result.stderr}"
                print(error_msg)
                app.logger.error(error_msg)
                return jsonify({"status": "error", "message": error_msg}), 500

            print("Poweroff command executed successfully (system is shutting down)")
            app.logger.info("Poweroff command executed successfully (system is shutting down)")
            print("="*80)

        elif platform.system() == "Windows":
            subprocess.Popen(["shutdown", "/s", "/t", "5"])
        else:
            return jsonify({"status": "error", "message": "Unsupported platform"}), 400

        return jsonify({"status": "success", "message": "System shutdown command executed successfully. System should shutdown shortly."})
    except subprocess.TimeoutExpired:
        error_msg = "Poweroff command timed out (this might be normal as system is shutting down)"
        print(error_msg)
        app.logger.warning(error_msg)
        return jsonify({"status": "success", "message": error_msg})
    except Exception as e:
        error_msg = f"Error shutting down system: {str(e)}"
        print(error_msg)
        app.logger.error(error_msg)
        import traceback
        traceback.print_exc()
        app.logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== STAY-ALIVE API ENDPOINTS ====================

@app.route('/api/stay_alive/status')
def stay_alive_status():
    """Get the current status of the stay-alive monitor"""
    try:
        status = get_stay_alive_status()
        return jsonify({"status": "success", **status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/stay_alive/start', methods=['POST'])
def stay_alive_start():
    """Start the stay-alive monitor"""
    try:
        success, message = start_stay_alive_monitor()
        return jsonify({"status": "success" if success else "info", "message": message})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/stay_alive/stop', methods=['POST'])
def stay_alive_stop():
    """Stop the stay-alive monitor"""
    try:
        success, message = stop_stay_alive_monitor()
        return jsonify({"status": "success" if success else "info", "message": message})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/stay_alive/test_connection')
def stay_alive_test_connection():
    """Test the network connectivity check"""
    try:
        is_connected = check_network_connectivity()
        return jsonify({
            "status": "success",
            "connected": is_connected,
            "ping_host": f"{STAY_ALIVE_PING_HOST}:{STAY_ALIVE_PING_PORT}",
            "last_successful_ping": stay_alive_last_successful_ping.isoformat() if stay_alive_last_successful_ping else None
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/stay_alive/logs')
def stay_alive_logs():
    """Get the stay-alive log entries"""
    try:
        return jsonify({
            "status": "success",
            "logs": stay_alive_log
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/sftp/transfer', methods=['POST'])
def sftp_transfer_images():
    """Transfer all images to FTP or sFTP server"""
    global app_settings

    try:
        # Check if FTP/sFTP is configured
        if not all([app_settings.get('ftp_server'),
                   app_settings.get('ftp_username'),
                   app_settings.get('ftp_password'),
                   app_settings.get('ftp_remote_path')]):
            return jsonify({
                "status": "error",
                "message": "FTP/sFTP not configured. Please fill in all FTP settings."
            }), 400

        protocol = app_settings.get('ftp_protocol', 'ftp').lower()

        print("="*80)
        print(f"{protocol.upper()} TRANSFER REQUESTED")
        print("="*80)
        app.logger.info(f"{protocol.upper()} transfer started")

        ftp_server = app_settings['ftp_server']
        ftp_port = app_settings.get('ftp_port', 21 if protocol == 'ftp' else 22)
        ftp_username = app_settings['ftp_username']
        ftp_password = app_settings['ftp_password']
        ftp_remote_path = app_settings['ftp_remote_path']

        print(f"Connecting to {ftp_username}@{ftp_server}:{ftp_port}")
        app.logger.info(f"Connecting to {ftp_username}@{ftp_server}:{ftp_port}")

        # Get all images (both ms and us formats)
        image_files = []
        image_files.extend(glob.glob(os.path.join(IMAGE_DIR, "*_exp*ms.png")))
        image_files.extend(glob.glob(os.path.join(IMAGE_DIR, "*_exp*us.png")))

        if not image_files:
            return jsonify({
                "status": "error",
                "message": "No images found to transfer"
            }), 404

        print(f"Found {len(image_files)} images to transfer")
        app.logger.info(f"Found {len(image_files)} images to transfer")

        # Validate connection parameters
        print(f"Protocol: {protocol.upper()}")
        print(f"Server: {ftp_server}")
        print(f"Port: {ftp_port}")
        print(f"Username: {ftp_username}")
        print(f"Remote path: {ftp_remote_path}")

        transferred = 0
        skipped = 0
        errors = 0

        if protocol == 'sftp':
            # sFTP transfer using paramiko
            try:
                import paramiko
            except ImportError as e:
                error_msg = "paramiko library not installed. Install with: pip install paramiko"
                print(f"ERROR: {error_msg}")
                app.logger.error(error_msg)
                return jsonify({"status": "error", "message": error_msg}), 500

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                # Connect to SSH server
                print(f"Attempting sFTP connection to {ftp_server}:{ftp_port}...")
                app.logger.info(f"Attempting sFTP connection to {ftp_server}:{ftp_port}...")

                try:
                    ssh.connect(
                        hostname=ftp_server,
                        port=ftp_port,
                        username=ftp_username,
                        password=ftp_password,
                        timeout=30,
                        allow_agent=False,
                        look_for_keys=False
                    )
                except paramiko.AuthenticationException as e:
                    error_msg = f"Authentication failed: Invalid username or password for {ftp_username}@{ftp_server}"
                    print(f"ERROR: {error_msg}")
                    app.logger.error(error_msg)
                    return jsonify({"status": "error", "message": error_msg}), 401
                except paramiko.SSHException as e:
                    error_msg = f"SSH error: {str(e)}"
                    print(f"ERROR: {error_msg}")
                    app.logger.error(error_msg)
                    return jsonify({"status": "error", "message": error_msg}), 500
                except socket.error as e:
                    error_msg = f"Network error connecting to {ftp_server}:{ftp_port} - {str(e)}. Check server address and port."
                    print(f"ERROR: {error_msg}")
                    app.logger.error(error_msg)
                    return jsonify({"status": "error", "message": error_msg}), 500
                except Exception as e:
                    error_msg = f"Connection failed: {str(e)}"
                    print(f"ERROR: {error_msg}")
                    app.logger.error(error_msg)
                    return jsonify({"status": "error", "message": error_msg}), 500

                print(f"✓ SSH connected successfully")
                app.logger.info("Connected to sFTP server successfully")

                # Open SFTP session
                sftp = ssh.open_sftp()

                # Create remote directory if it doesn't exist
                try:
                    sftp.chdir(ftp_remote_path)
                except IOError:
                    # Directory doesn't exist, create it
                    dirs = []
                    current_path = ftp_remote_path
                    while current_path and current_path != '/':
                        dirs.insert(0, current_path)
                        current_path = os.path.dirname(current_path)

                    for dir_path in dirs:
                        try:
                            sftp.stat(dir_path)
                        except IOError:
                            sftp.mkdir(dir_path)
                            print(f"Created remote directory: {dir_path}")

                    sftp.chdir(ftp_remote_path)

                print(f"Changed to remote directory: {ftp_remote_path}")
                app.logger.info(f"Changed to remote directory: {ftp_remote_path}")

                # Upload files
                for image_path in image_files:
                    try:
                        filename = os.path.basename(image_path)

                        # Check if file already exists on remote
                        try:
                            sftp.stat(filename)
                            print(f"Skipping (already exists): {filename}")
                            skipped += 1
                            continue
                        except IOError:
                            pass

                        # Upload the file
                        print(f"Uploading: {filename}")
                        sftp.put(image_path, filename)
                        transferred += 1

                    except Exception as e:
                        print(f"Error transferring {filename}: {str(e)}")
                        app.logger.error(f"Error transferring {filename}: {str(e)}")
                        errors += 1

                # Close connections
                sftp.close()
                ssh.close()

            finally:
                try:
                    sftp.close()
                except:
                    pass
                try:
                    ssh.close()
                except:
                    pass

        else:
            # Regular FTP transfer
            from ftplib import FTP, error_perm

            ftp = None
            try:
                print(f"Attempting FTP connection to {ftp_server}:{ftp_port}...")
                app.logger.info(f"Attempting FTP connection to {ftp_server}:{ftp_port}...")

                ftp = FTP()

                try:
                    ftp.connect(ftp_server, ftp_port, timeout=30)
                    print(f"✓ FTP connection established")
                    app.logger.info(f"FTP connection established to {ftp_server}:{ftp_port}")
                except socket.gaierror as e:
                    error_msg = f"DNS lookup failed for {ftp_server}. Check server address."
                    print(f"ERROR: {error_msg}")
                    app.logger.error(f"{error_msg} - {str(e)}")
                    return jsonify({"status": "error", "message": error_msg}), 500
                except socket.timeout as e:
                    error_msg = f"Connection timeout to {ftp_server}:{ftp_port}. Check if server is reachable and port is correct."
                    print(f"ERROR: {error_msg}")
                    app.logger.error(f"{error_msg} - {str(e)}")
                    return jsonify({"status": "error", "message": error_msg}), 500
                except socket.error as e:
                    error_msg = f"Network error connecting to {ftp_server}:{ftp_port} - {str(e)}"
                    print(f"ERROR: {error_msg}")
                    app.logger.error(error_msg)
                    return jsonify({"status": "error", "message": error_msg}), 500
                except Exception as e:
                    error_msg = f"FTP connection failed: {str(e)}"
                    print(f"ERROR: {error_msg}")
                    app.logger.error(error_msg)
                    return jsonify({"status": "error", "message": error_msg}), 500

                try:
                    ftp.login(ftp_username, ftp_password)
                    print(f"✓ FTP login successful as {ftp_username}")
                    app.logger.info(f"FTP login successful as {ftp_username}")
                except error_perm as e:
                    error_msg = f"Authentication failed: Invalid username or password for {ftp_username}"
                    print(f"ERROR: {error_msg}")
                    app.logger.error(f"{error_msg} - {str(e)}")
                    return jsonify({"status": "error", "message": error_msg}), 401
                except Exception as e:
                    error_msg = f"FTP login failed: {str(e)}"
                    print(f"ERROR: {error_msg}")
                    app.logger.error(error_msg)
                    return jsonify({"status": "error", "message": error_msg}), 500

                print(f"✓ FTP connected successfully")
                app.logger.info("Connected to FTP server successfully")

                # Create and change to remote directory
                try:
                    ftp.cwd(ftp_remote_path)
                    print(f"✓ Changed to remote directory: {ftp_remote_path}")
                    app.logger.info(f"Changed to remote directory: {ftp_remote_path}")
                except error_perm as e:
                    # Directory doesn't exist, try to create it
                    print(f"Directory {ftp_remote_path} doesn't exist, creating...")
                    app.logger.info(f"Directory {ftp_remote_path} doesn't exist, creating...")

                    dirs = ftp_remote_path.strip('/').split('/')
                    current = ''
                    for dir_name in dirs:
                        current += '/' + dir_name
                        try:
                            ftp.cwd(current)
                            print(f"  ✓ Directory exists: {current}")
                        except error_perm:
                            try:
                                ftp.mkd(current)
                                ftp.cwd(current)
                                print(f"  ✓ Created remote directory: {current}")
                                app.logger.info(f"Created remote directory: {current}")
                            except error_perm as e:
                                error_msg = f"Permission denied: Cannot create directory {current}. Check FTP user permissions."
                                print(f"ERROR: {error_msg}")
                                app.logger.error(f"{error_msg} - {str(e)}")
                                return jsonify({"status": "error", "message": error_msg}), 403
                            except Exception as e:
                                error_msg = f"Could not create directory {current}: {str(e)}"
                                print(f"ERROR: {error_msg}")
                                app.logger.error(error_msg)
                                return jsonify({"status": "error", "message": error_msg}), 500

                    print(f"✓ Successfully created and changed to: {ftp_remote_path}")
                    app.logger.info(f"Successfully created and changed to: {ftp_remote_path}")

                # Get list of existing files
                existing_files = []
                try:
                    existing_files = ftp.nlst()
                except:
                    pass

                # Upload files
                for image_path in image_files:
                    try:
                        filename = os.path.basename(image_path)

                        # Check if file already exists
                        if filename in existing_files:
                            print(f"Skipping (already exists): {filename}")
                            skipped += 1
                            continue

                        # Upload the file
                        print(f"Uploading: {filename}")
                        with open(image_path, 'rb') as f:
                            ftp.storbinary(f'STOR {filename}', f)
                        transferred += 1

                    except Exception as e:
                        print(f"Error transferring {filename}: {str(e)}")
                        app.logger.error(f"Error transferring {filename}: {str(e)}")
                        errors += 1

                # Close connection
                ftp.quit()

            except Exception as e:
                if ftp:
                    try:
                        ftp.quit()
                    except:
                        pass
                raise

        print("="*80)
        print(f"Transfer complete: {transferred} uploaded, {skipped} skipped, {errors} errors")
        print("="*80)
        app.logger.info(f"Transfer complete: {transferred} uploaded, {skipped} skipped, {errors} errors")

        return jsonify({
            "status": "success",
            "message": f"Transfer complete: {transferred} uploaded, {skipped} skipped, {errors} errors",
            "transferred": transferred,
            "skipped": skipped,
            "errors": errors
        })

    except ImportError as e:
        error_msg = f"Required library not installed: {str(e)}"
        print(error_msg)
        app.logger.error(error_msg)
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 500
    except Exception as e:
        error_msg = f"{protocol.upper() if 'protocol' in locals() else 'FTP'} transfer failed: {str(e)}"
        print(error_msg)
        app.logger.error(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 500
def get_cpu_temperature():
    """Get CPU temperature based on the platform."""
    temp = None

    if platform.system() == "Linux":
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp = float(f.read()) / 1000.0
        except (IOError, ValueError):
            try:
                import subprocess
                output = subprocess.check_output(["vcgencmd", "measure_temp"])
                temp = float(output.decode("utf-8").replace("temp=", "").replace("'C", ""))
            except (subprocess.CalledProcessError, ImportError, ValueError):
                temp = None

    elif platform.system() == "Windows":
        try:
            import wmi
            w = wmi.WMI()
            temperature_info = w.MSAcpi_ThermalZoneTemperature()[0]
            temp = temperature_info.CurrentTemperature / 10.0 - 273.15
        except:
            temp = None

    return temp


def get_directory_size(path):
    """Get the total size of a directory in bytes."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total_size += os.path.getsize(fp)
    return total_size


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Get or update application settings"""
    global app_settings

    if request.method == 'GET':
        return jsonify(app_settings)

    elif request.method == 'POST':
        try:
            data = request.get_json(force=True)

            # Update settings
            if 'latitude' in data:
                app_settings['latitude'] = data['latitude']
            if 'longitude' in data:
                app_settings['longitude'] = data['longitude']
            if 'timezone' in data:
                app_settings['timezone'] = data['timezone']
            if 'dst_enabled' in data:
                app_settings['dst_enabled'] = data['dst_enabled']
            if 'openweather_api_key' in data:
                app_settings['openweather_api_key'] = data['openweather_api_key']
            if 'min_exposure_ms' in data:
                app_settings['min_exposure_ms'] = max(0.034, float(data['min_exposure_ms']))
            if 'max_exposure_ms' in data:
                app_settings['max_exposure_ms'] = max(100, int(data['max_exposure_ms']))
            if 'capture_daytime' in data:
                app_settings['capture_daytime'] = bool(data['capture_daytime'])
            if 'capture_civil_twilight' in data:
                app_settings['capture_civil_twilight'] = bool(data['capture_civil_twilight'])
            if 'capture_nautical_twilight' in data:
                app_settings['capture_nautical_twilight'] = bool(data['capture_nautical_twilight'])
            if 'capture_astronomical_darkness' in data:
                app_settings['capture_astronomical_darkness'] = bool(data['capture_astronomical_darkness'])
            if 'ftp_protocol' in data:
                app_settings['ftp_protocol'] = data['ftp_protocol']
            if 'ftp_server' in data:
                app_settings['ftp_server'] = data['ftp_server']
            if 'ftp_port' in data:
                app_settings['ftp_port'] = int(data['ftp_port']) if data['ftp_port'] else 21
            if 'ftp_username' in data:
                app_settings['ftp_username'] = data['ftp_username']
            if 'ftp_password' in data:
                app_settings['ftp_password'] = data['ftp_password']
            if 'ftp_remote_path' in data:
                app_settings['ftp_remote_path'] = data['ftp_remote_path']
            if 'compass_rotation' in data:
                app_settings['compass_rotation'] = int(data['compass_rotation']) % 360
                print(f"Compass rotation set to: {app_settings['compass_rotation']}")
            if 'compass_enabled' in data:
                app_settings['compass_enabled'] = bool(data['compass_enabled'])
                print(f"Compass enabled set to: {app_settings['compass_enabled']}")
            if 'starmap_enabled' in data:
                app_settings['starmap_enabled'] = bool(data['starmap_enabled'])
                print(f"Starmap enabled set to: {app_settings['starmap_enabled']}")
            if 'starmap_magnitude_limit' in data:
                app_settings['starmap_magnitude_limit'] = min(7.0, max(1.0, float(data['starmap_magnitude_limit'])))
            if 'starmap_show_names' in data:
                app_settings['starmap_show_names'] = bool(data['starmap_show_names'])
            if 'starmap_show_constellations' in data:
                app_settings['starmap_show_constellations'] = bool(data['starmap_show_constellations'])
            if 'starmap_opacity' in data:
                app_settings['starmap_opacity'] = min(1.0, max(0.1, float(data['starmap_opacity'])))
            if 'starmap_color' in data:
                app_settings['starmap_color'] = data['starmap_color']
            if 'starmap_rotation_adjust' in data:
                app_settings['starmap_rotation_adjust'] = max(-180, min(180, int(data['starmap_rotation_adjust'])))
            if 'starmap_offset_x' in data:
                app_settings['starmap_offset_x'] = max(-500, min(500, int(data['starmap_offset_x'])))
            if 'starmap_offset_y' in data:
                app_settings['starmap_offset_y'] = max(-500, min(500, int(data['starmap_offset_y'])))
            if 'starmap_scale_x' in data:
                app_settings['starmap_scale_x'] = max(0.5, min(2.0, float(data['starmap_scale_x'])))
            if 'starmap_scale_y' in data:
                app_settings['starmap_scale_y'] = max(0.5, min(2.0, float(data['starmap_scale_y'])))

            # Save configuration to file
            save_config()

            return jsonify({
                "status": "success",
                "message": "Settings saved successfully"
            })
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"Error saving settings: {str(e)}"
            }), 500


@app.route('/api/solar_info')
def api_solar_info():
    """Calculate and return solar information based on location settings"""
    global app_settings

    if app_settings['latitude'] is None or app_settings['longitude'] is None:
        return jsonify({
            "status": "error",
            "message": "Location not set"
        })

    try:
        from datetime import datetime, timedelta
        import math

        # Get current date
        now = datetime.now()
        lat = app_settings['latitude']
        lon = app_settings['longitude']

        # Calculate solar times (simplified calculation)
        # For production, consider using a library like ephem or astral

        def calculate_solar_noon(lon):
            """Calculate solar noon in UTC"""
            return 12.0 - (lon / 15.0)

        def calculate_sunrise_sunset(lat, lon, date):
            """Simplified sunrise/sunset calculation"""
            # This is a basic approximation. For accurate results, use astral or ephem library
            day_of_year = date.timetuple().tm_yday

            # Solar declination
            declination = 23.45 * math.sin(math.radians((360/365) * (day_of_year - 81)))

            # Hour angle
            lat_rad = math.radians(lat)
            dec_rad = math.radians(declination)

            cos_hour_angle = -math.tan(lat_rad) * math.tan(dec_rad)

            # Check if sun rises/sets
            if cos_hour_angle > 1:
                # Polar night
                return None, None
            elif cos_hour_angle < -1:
                # Midnight sun
                return "00:00", "23:59"

            hour_angle = math.degrees(math.acos(cos_hour_angle))

            solar_noon = calculate_solar_noon(lon)
            sunrise_hour = solar_noon - (hour_angle / 15.0)
            sunset_hour = solar_noon + (hour_angle / 15.0)

            # Apply timezone offset
            tz_offset = app_settings.get('timezone', 0) or 0
            if app_settings.get('dst_enabled'):
                tz_offset += 1

            sunrise_hour += tz_offset
            sunset_hour += tz_offset

            # Format times
            def format_time(hour):
                hour = hour % 24
                hours = int(hour)
                minutes = int((hour - hours) * 60)
                return f"{hours:02d}:{minutes:02d}"

            return format_time(sunrise_hour), format_time(sunset_hour)

        sunrise, sunset = calculate_sunrise_sunset(lat, lon, now)

        if sunrise is None or sunset is None:
            return jsonify({
                "status": "error",
                "message": "Unable to calculate solar times for this location"
            })

        # Calculate twilight times (6°, 12°, 18° below horizon)
        # For simplicity, adding approximate offsets
        def parse_time(time_str):
            h, m = map(int, time_str.split(':'))
            return h + m/60

        def format_time(hour):
            hour = hour % 24
            hours = int(hour)
            minutes = int((hour - hours) * 60)
            return f"{hours:02d}:{minutes:02d}"

        sunset_hour = parse_time(sunset)

        # Approximate twilight durations (varies by latitude)
        civil_twilight = format_time(sunset_hour + 0.5)  # ~30 min after sunset
        nautical_twilight = format_time(sunset_hour + 1.0)  # ~1 hour after sunset
        astronomical_twilight = format_time(sunset_hour + 1.5)  # ~1.5 hours after sunset

        return jsonify({
            "status": "success",
            "sunrise": sunrise,
            "sunset": sunset,
            "civil_twilight_end": civil_twilight,
            "nautical_twilight_end": nautical_twilight,
            "astronomical_twilight_end": astronomical_twilight
        })

    except Exception as e:
        app.logger.error(f"Error calculating solar info: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error: {str(e)}"
        }), 500


@app.route('/api/night_info')
def api_night_info():
    """Calculate and return night sky information including moon phase and imaging time"""
    global app_settings

    if app_settings['latitude'] is None or app_settings['longitude'] is None:
        return jsonify({
            "status": "error",
            "message": "Location not set. Please configure your location in the Control Panel."
        })

    try:
        from datetime import datetime, timedelta
        import math

        now = datetime.now()
        lat = app_settings['latitude']
        lon = app_settings['longitude']

        # Calculate solar times using the same function from api_solar_info
        def calculate_solar_noon(lon):
            return 12.0 - (lon / 15.0)

        def calculate_sunrise_sunset(lat, lon, date):
            day_of_year = date.timetuple().tm_yday
            declination = 23.45 * math.sin(math.radians((360/365) * (day_of_year - 81)))
            lat_rad = math.radians(lat)
            dec_rad = math.radians(declination)
            cos_hour_angle = -math.tan(lat_rad) * math.tan(dec_rad)

            if cos_hour_angle > 1:
                return None, None
            elif cos_hour_angle < -1:
                return "00:00", "23:59"

            hour_angle = math.degrees(math.acos(cos_hour_angle))
            solar_noon = calculate_solar_noon(lon)
            sunrise_hour = solar_noon - (hour_angle / 15.0)
            sunset_hour = solar_noon + (hour_angle / 15.0)

            tz_offset = app_settings.get('timezone', 0) or 0
            if app_settings.get('dst_enabled'):
                tz_offset += 1

            sunrise_hour += tz_offset
            sunset_hour += tz_offset

            def format_time(hour):
                hour = hour % 24
                hours = int(hour)
                minutes = int((hour - hours) * 60)
                return f"{hours:02d}:{minutes:02d}"

            return format_time(sunrise_hour), format_time(sunset_hour)

        sunrise, sunset = calculate_sunrise_sunset(lat, lon, now)

        if sunrise is None or sunset is None:
            return jsonify({
                "status": "error",
                "message": "Unable to calculate solar times for this location"
            })

        # Calculate twilight times
        def parse_time(time_str):
            h, m = map(int, time_str.split(':'))
            return h + m/60

        def format_time(hour):
            hour = hour % 24
            hours = int(hour)
            minutes = int((hour - hours) * 60)
            return f"{hours:02d}:{minutes:02d}"

        sunset_hour = parse_time(sunset)
        astronomical_twilight = format_time(sunset_hour + 1.5)

        # Calculate moon phase
        def calculate_moon_phase(date):
            """Calculate moon phase and illumination percentage"""
            # Known new moon date
            known_new_moon = datetime(2000, 1, 6, 18, 14)
            synodic_month = 29.53058867  # days

            days_since = (date - known_new_moon).total_seconds() / 86400
            moon_age = days_since % synodic_month
            phase = moon_age / synodic_month

            # Calculate illumination
            illumination = (1 - math.cos(2 * math.pi * phase)) / 2 * 100

            # Determine phase name and icon
            if phase < 0.0625:
                phase_name = "New Moon"
                icon = "🌑"
            elif phase < 0.1875:
                phase_name = "Waxing Crescent"
                icon = "🌒"
            elif phase < 0.3125:
                phase_name = "First Quarter"
                icon = "🌓"
            elif phase < 0.4375:
                phase_name = "Waxing Gibbous"
                icon = "🌔"
            elif phase < 0.5625:
                phase_name = "Full Moon"
                icon = "🌕"
            elif phase < 0.6875:
                phase_name = "Waning Gibbous"
                icon = "🌖"
            elif phase < 0.8125:
                phase_name = "Last Quarter"
                icon = "🌗"
            elif phase < 0.9375:
                phase_name = "Waning Crescent"
                icon = "🌘"
            else:
                phase_name = "New Moon"
                icon = "🌑"

            return {
                "phase_name": phase_name,
                "icon": icon,
                "illumination": f"{illumination:.0f}% illuminated"
            }

        moon_data = calculate_moon_phase(now)

        # Calculate imaging time remaining (only astronomical darkness)
        current_hour = now.hour + now.minute / 60
        sunrise_hour_float = parse_time(sunrise)
        sunset_hour_float = parse_time(sunset)
        astro_twilight_float = parse_time(astronomical_twilight)

        # Calculate when astronomical twilight begins in the morning (approximately 1.5 hours before sunrise)
        sunrise_hour_float_prev = sunrise_hour_float
        if sunrise_hour_float < 1.5:
            sunrise_hour_float_prev = sunrise_hour_float + 24
        astro_twilight_morning = sunrise_hour_float_prev - 1.5

        # Determine if we're currently in astronomical darkness
        is_dark = False
        if astro_twilight_float < sunrise_hour_float:
            # Normal case: darkness period doesn't cross midnight
            is_dark = current_hour >= astro_twilight_float and current_hour < astro_twilight_morning
        else:
            # Darkness period crosses midnight
            is_dark = current_hour >= astro_twilight_float or current_hour < astro_twilight_morning

        if is_dark:
            # We're in darkness now - calculate time until morning twilight begins
            if current_hour >= astro_twilight_float:
                # Same night
                hours_remaining = (24 - current_hour) + astro_twilight_morning if astro_twilight_morning < current_hour else astro_twilight_morning - current_hour
            else:
                # Early morning before dawn
                hours_remaining = astro_twilight_morning - current_hour
            detail = "of darkness remaining"
        else:
            # We're in daylight - calculate time until next darkness
            if current_hour < sunset_hour_float:
                hours_remaining = astro_twilight_float - current_hour
                detail = "until darkness begins"
            else:
                # Between sunset and astro twilight
                hours_remaining = astro_twilight_float - current_hour
                if hours_remaining < 0:
                    # After midnight case
                    hours_remaining = (24 - current_hour) + astro_twilight_float
                detail = "until darkness begins"

        # Format imaging time
        hours = int(hours_remaining)
        minutes = int((hours_remaining - hours) * 60)
        imaging_time_str = f"{hours}h {minutes}m"

        # Fetch weather data from OpenWeather API
        weather_data = {
            "description": "Not available",
            "icon": "🌤",
            "clouds": None,
            "rain": None,
            "temperature": None,
            "humidity": None,
            "pressure": None,
            "wind_speed": None,
            "wind_gust": None
        }

        if REQUESTS_AVAILABLE and app_settings.get('openweather_api_key') and app_settings['openweather_api_key'].strip():
            try:
                api_key = app_settings['openweather_api_key']

                # Strip any whitespace from API key
                api_key = api_key.strip() if isinstance(api_key, str) else api_key

                # Check if API key is empty after stripping
                if not api_key:
                    print("OpenWeather API key is empty after stripping whitespace")
                    weather_data["description"] = "No API key"
                else:
                    weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"

                    print(f"Fetching weather data from OpenWeather API for lat={lat}, lon={lon}")

                    response = requests.get(weather_url, timeout=10)

                    print(f"OpenWeather API response status: {response.status_code}")

                    if response.status_code == 200:
                        weather_json = response.json()

                        print(f"Weather data received: {weather_json.get('weather', [{}])[0].get('description', 'Unknown')}")

                        # Extract weather information
                        weather_data["description"] = weather_json.get("weather", [{}])[0].get("description", "Unknown").capitalize()
                        weather_data["temperature"] = weather_json.get("main", {}).get("temp")
                        weather_data["humidity"] = weather_json.get("main", {}).get("humidity")
                        weather_data["pressure"] = weather_json.get("main", {}).get("pressure")
                        weather_data["clouds"] = weather_json.get("clouds", {}).get("all")  # Cloud coverage percentage

                        # Rain data (if available)
                        if "rain" in weather_json:
                            weather_data["rain"] = weather_json["rain"].get("1h", 0)  # Rain volume for last hour
                        else:
                            weather_data["rain"] = 0

                        # Wind data
                        weather_data["wind_speed"] = weather_json.get("wind", {}).get("speed")
                        weather_data["wind_gust"] = weather_json.get("wind", {}).get("gust")

                        # Map OpenWeather icon codes to emoji
                        weather_code = weather_json.get("weather", [{}])[0].get("icon", "01d")
                        icon_map = {
                            "01d": "☀️", "01n": "🌙",  # Clear sky
                            "02d": "🌤", "02n": "🌤",  # Few clouds
                            "03d": "☁️", "03n": "☁️",  # Scattered clouds
                            "04d": "☁️", "04n": "☁️",  # Broken clouds
                            "09d": "🌧", "09n": "🌧",  # Shower rain
                            "10d": "🌦", "10n": "🌦",  # Rain
                            "11d": "⛈", "11n": "⛈",   # Thunderstorm
                            "13d": "🌨", "13n": "🌨",  # Snow
                            "50d": "🌫", "50n": "🌫"   # Mist
                        }
                        weather_data["icon"] = icon_map.get(weather_code, "🌤")
                    else:
                        error_msg = f"OpenWeather API error: {response.status_code}"
                        try:
                            error_data = response.json()
                            error_msg += f" - {error_data.get('message', 'Unknown error')}"
                        except:
                            error_msg += f" - {response.text[:200]}"
                        print(error_msg)
                        weather_data["description"] = f"API Error ({response.status_code})"

            except requests.exceptions.Timeout:
                print("OpenWeather API request timed out")
                weather_data["description"] = "Request timeout"
            except requests.exceptions.RequestException as e:
                print(f"OpenWeather API request failed: {str(e)}")
                weather_data["description"] = "Connection error"
            except Exception as e:
                print(f"Error fetching weather data: {str(e)}")
                import traceback
                traceback.print_exc()
                weather_data["description"] = "Error fetching data"
        elif not REQUESTS_AVAILABLE:
            print("Requests module not available - cannot fetch weather data")
            weather_data["description"] = "Requests module not installed"
        else:
            print("No OpenWeather API key configured")
            weather_data["description"] = "No API key configured"

        return jsonify({
            "status": "success",
            "sunrise": sunrise,
            "sunset": sunset,
            "astronomical_twilight_end": astronomical_twilight,
            "moon_phase_name": moon_data["phase_name"],
            "moon_icon": moon_data["icon"],
            "moon_illumination": moon_data["illumination"],
            "imaging_time_remaining": imaging_time_str,
            "imaging_time_detail": detail,
            "weather_description": weather_data["description"],
            "weather_icon": weather_data["icon"],
            "weather_clouds": weather_data["clouds"],
            "weather_rain": weather_data["rain"],
            "weather_temperature": weather_data["temperature"],
            "weather_humidity": weather_data["humidity"],
            "weather_pressure": weather_data["pressure"],
            "weather_wind_speed": weather_data["wind_speed"],
            "weather_wind_gust": weather_data["wind_gust"]
        })

    except Exception as e:
        app.logger.error(f"Error calculating night info: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error: {str(e)}"
        }), 500


@app.route('/api/starmap')
def api_starmap():
    """Calculate star positions for the starmap overlay

    Optional query parameters:
        timestamp: ISO format timestamp (e.g., '2024-01-15T20:30:00') to calculate
                   star positions for a specific time instead of current time.
                   Used for historical images.
        skip_enabled_check: If 'true', skip the starmap_enabled check (for detail page toggle)
    """
    global app_settings

    # Camera parameters from plate solving
    CAMERA_FOV_RADIUS = 54.211  # degrees from zenith
    PIXEL_SCALE = 244  # arcsec/pixel
    CAMERA_ROTATION = 91.6  # degrees E of N
    IMAGE_WIDTH = 1280  # pixels (estimated)
    IMAGE_HEIGHT = 960  # pixels (estimated)

    if app_settings['latitude'] is None or app_settings['longitude'] is None:
        return jsonify({
            "status": "error",
            "message": "Location not set. Please configure your location in the Control Panel."
        })

    # Check if we should skip the enabled check (for image detail page toggle)
    skip_enabled_check = request.args.get('skip_enabled_check', 'false').lower() == 'true'

    if not skip_enabled_check and not app_settings.get('starmap_enabled', False):
        return jsonify({
            "status": "disabled",
            "message": "Star map is disabled"
        })

    try:
        import math
        from datetime import datetime

        lat = app_settings['latitude']
        lon = app_settings['longitude']
        mag_limit = app_settings.get('starmap_magnitude_limit', 4.0)

        # Get timestamp - either from query parameter or current UTC time
        timestamp_param = request.args.get('timestamp')
        if timestamp_param:
            try:
                # Parse ISO format timestamp
                now = datetime.fromisoformat(timestamp_param.replace('Z', '+00:00').replace('+00:00', ''))
            except ValueError:
                return jsonify({
                    "status": "error",
                    "message": f"Invalid timestamp format: {timestamp_param}. Use ISO format (e.g., 2024-01-15T20:30:00)"
                })
        else:
            now = datetime.utcnow()

        # Calculate Julian Date
        def julian_date(dt):
            """Calculate Julian Date from datetime"""
            a = (14 - dt.month) // 12
            y = dt.year + 4800 - a
            m = dt.month + 12 * a - 3
            jdn = dt.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
            jd = jdn + (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0
            return jd

        # Calculate Local Sidereal Time
        def calculate_lst(lon, dt):
            """Calculate Local Sidereal Time in hours"""
            jd = julian_date(dt)
            # Julian centuries from J2000.0
            t = (jd - 2451545.0) / 36525.0
            # Greenwich Mean Sidereal Time in degrees
            gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * t * t - t * t * t / 38710000.0
            gmst = gmst % 360.0
            # Local Sidereal Time
            lst = gmst + lon
            lst = lst % 360.0
            return lst / 15.0  # Convert to hours

        # Convert RA/Dec to Alt/Az
        def equatorial_to_altaz(ra_hours, dec_deg, lat_deg, lst_hours):
            """Convert equatorial coordinates to altitude/azimuth"""
            # Convert to radians
            ra = math.radians(ra_hours * 15.0)  # RA hours to degrees to radians
            dec = math.radians(dec_deg)
            lat = math.radians(lat_deg)
            lst = math.radians(lst_hours * 15.0)  # LST hours to degrees to radians

            # Hour angle
            ha = lst - ra

            # Calculate altitude
            sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(ha)
            alt = math.asin(max(-1.0, min(1.0, sin_alt)))

            # Calculate azimuth
            cos_az = (math.sin(dec) - math.sin(alt) * math.sin(lat)) / (math.cos(alt) * math.cos(lat))
            cos_az = max(-1.0, min(1.0, cos_az))
            az = math.acos(cos_az)

            if math.sin(ha) > 0:
                az = 2 * math.pi - az

            return math.degrees(alt), math.degrees(az)

        # Gnomonic projection for zenith-pointing camera
        def gnomonic_projection(alt, az, rotation_deg, img_width, img_height, pixel_scale):
            """Project alt/az to pixel coordinates using gnomonic projection"""
            # Zenith distance (90 - altitude)
            zd = 90.0 - alt

            if zd > CAMERA_FOV_RADIUS:
                return None, None  # Outside FOV

            # Convert to radians
            zd_rad = math.radians(zd)
            az_rad = math.radians(az)
            rot_rad = math.radians(rotation_deg)

            # Gnomonic projection
            r = math.tan(zd_rad)

            # Apply rotation (camera orientation)
            az_rotated = az_rad - rot_rad

            # Calculate x, y in tangent plane (radians)
            x_tan = r * math.sin(az_rotated)
            y_tan = -r * math.cos(az_rotated)  # Negative because y increases downward on image

            # Convert to pixels (r is in radians, need to convert to arcsec then to pixels)
            # pixel_scale is arcsec/pixel
            if pixel_scale == 0:
                return None, None  # Invalid pixel scale

            scale = (180.0 / math.pi) * 3600.0 / pixel_scale  # radians to pixels

            x_pix = x_tan * scale + img_width / 2
            y_pix = y_tan * scale + img_height / 2

            return x_pix, y_pix

        # Load star catalog
        import os
        catalog_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'data', 'bright_stars.json')

        if not os.path.exists(catalog_path):
            return jsonify({
                "status": "error",
                "message": "Star catalog not found"
            })

        with open(catalog_path, 'r') as f:
            catalog = json.load(f)

        # Calculate LST
        lst = calculate_lst(lon, now)

        # Process each star
        visible_stars = []
        for star in catalog['stars']:
            # Skip stars fainter than magnitude limit
            if star['mag'] > mag_limit:
                continue

            # Convert RA/Dec to Alt/Az
            alt, az = equatorial_to_altaz(star['ra'], star['dec'], lat, lst)

            # Skip stars below horizon
            if alt < 0:
                continue

            # Project to pixel coordinates
            x, y = gnomonic_projection(alt, az, CAMERA_ROTATION, IMAGE_WIDTH, IMAGE_HEIGHT, PIXEL_SCALE)

            if x is not None and y is not None:
                visible_stars.append({
                    "name": star.get('name', ''),
                    "bayer": star.get('bayer', ''),
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "mag": star['mag'],
                    "alt": round(alt, 1),
                    "az": round(az, 1)
                })

        # Build constellation lines if enabled
        constellation_lines = []
        show_constellations = app_settings.get('starmap_show_constellations', True)

        if show_constellations:
            # Create a lookup dictionary for star positions by name
            star_positions = {}
            for star in visible_stars:
                if star['name']:
                    star_positions[star['name']] = {'x': star['x'], 'y': star['y']}
                if star.get('bayer'):
                    star_positions[star['bayer']] = {'x': star['x'], 'y': star['y']}

            # Load constellation lines data
            constellation_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'data', 'constellation_lines.json')

            if os.path.exists(constellation_path):
                with open(constellation_path, 'r') as f:
                    constellation_data = json.load(f)

                for constellation in constellation_data.get('constellations', []):
                    for line in constellation.get('lines', []):
                        if len(line) == 2:
                            star1_name, star2_name = line
                            # Check if both stars are visible
                            star1_pos = star_positions.get(star1_name)
                            star2_pos = star_positions.get(star2_name)

                            if star1_pos and star2_pos:
                                constellation_lines.append({
                                    'x1': star1_pos['x'],
                                    'y1': star1_pos['y'],
                                    'x2': star2_pos['x'],
                                    'y2': star2_pos['y'],
                                    'constellation': constellation.get('abbr', '')
                                })

        return jsonify({
            "status": "success",
            "timestamp": now.isoformat(),
            "lst": round(lst, 4),
            "star_count": len(visible_stars),
            "line_count": len(constellation_lines),
            "fov_radius": CAMERA_FOV_RADIUS,
            "image_width": IMAGE_WIDTH,
            "image_height": IMAGE_HEIGHT,
            "stars": visible_stars,
            "constellation_lines": constellation_lines
        })

    except Exception as e:
        app.logger.error(f"Error calculating star positions: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error: {str(e)}"
        }), 500


# Load configuration when module is imported (works with both gunicorn and direct run)
print("Loading configuration...")
load_config()
print(f"Configuration loaded: Capture interval = {capture_interval}s")
print(f"Location: lat={app_settings['latitude']}, lon={app_settings['longitude']}")

# Start background capture automatically on startup if it was enabled before
if background_capture_enabled:
    print("Background capture was enabled, restarting...")
    start_background_capture()
else:
    print("Background capture is disabled")

# Start stay-alive monitor automatically on startup
if stay_alive_enabled:
    print("Starting stay-alive network monitor...")
    start_stay_alive_monitor()
    print("Stay-alive monitor started")
else:
    print("Stay-alive monitor is disabled")

if __name__ == '__main__':
    # This block only runs when executed directly with python3 flask_app.py
    # When running with gunicorn, the above code already ran during import
    app.run(host='0.0.0.0', port=5000, debug=False)
