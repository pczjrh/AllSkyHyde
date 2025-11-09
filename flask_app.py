# app.py
from flask import Flask, render_template, send_from_directory, jsonify, request, redirect, url_for
import os
import glob
import re
import json
import subprocess
from datetime import datetime
import threading
import time
import shutil
import psutil
import platform

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

# Global settings storage
app_settings = {
    "latitude": None,
    "longitude": None,
    "timezone": None,
    "dst_enabled": False,
    "openweather_api_key": None
}


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

                # Load paths (optional, can be overridden)
                if 'image_dir' in config:
                    IMAGE_DIR = config['image_dir']
                if 'script_path' in config:
                    SCRIPT_PATH = config['script_path']

                print(f"Configuration loaded from {CONFIG_FILE}")
                print(f"Settings: lat={app_settings.get('latitude')}, lon={app_settings.get('longitude')}, api_key={'set' if app_settings.get('openweather_api_key') else 'not set'}")
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
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)

        print(f"Configuration saved to {CONFIG_FILE}")
        print(f"Settings: lat={app_settings.get('latitude')}, lon={app_settings.get('longitude')}, api_key={'set' if app_settings.get('openweather_api_key') else 'not set'}")
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
        "exposure_ms": None
    }

    # Extract timestamp (format: YYYYMMDD_HHMMSS_expXXXms.png)
    timestamp_match = re.search(r'(\d{8}_\d{6})', filename)
    if timestamp_match:
        timestamp_str = timestamp_match.group(1)
        try:
            dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            metadata["timestamp"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    # Extract exposure time
    exposure_match = re.search(r'exp(\d+)ms', filename)
    if exposure_match:
        metadata["exposure_ms"] = int(exposure_match.group(1))

    return metadata


def get_all_images():
    """Get all ZWO images with metadata, sorted by date (newest first)"""
    # Match files with pattern: YYYYMMDD_HHMMSS_expXXXms.png
    image_pattern = os.path.join(IMAGE_DIR, "*_exp*ms.png")
    image_files = glob.glob(image_pattern)

    images = []
    for img_path in image_files:
        filename = os.path.basename(img_path)
        metadata = extract_metadata_from_filename(filename)

        # Get file stats
        stats = os.stat(img_path)
        file_size = stats.st_size / (1024 * 1024)  # Convert to MB

        images.append({
            "filename": filename,
            "path": img_path,
            "timestamp": metadata["timestamp"],
            "exposure_ms": metadata["exposure_ms"],
            "size_mb": round(file_size, 2),
            "modified": datetime.fromtimestamp(stats.st_mtime)
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


def background_capture_loop():
    """Background thread that captures images at regular intervals"""
    global is_capturing, stop_capture_flag, capture_log, last_capture_time
    
    capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Background capture started (interval: {capture_interval}s)")
    
    while not stop_capture_flag:
        is_capturing = True
        
        # Run capture
        success = run_single_capture()
        
        is_capturing = False
        
        if success:
            capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting {capture_interval} seconds until next capture...")
        else:
            capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Capture failed, will retry in {capture_interval} seconds...")
        
        # Wait for the interval (check stop flag every second)
        for _ in range(capture_interval):
            if stop_capture_flag:
                break
            time.sleep(1)
    
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
    
    return render_template('index.html',
                           latest_image=latest_image,
                           capture_interval=capture_interval,
                           last_capture_timestamp=last_capture_timestamp,
                           background_running=background_capture_enabled)


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
    image_path = os.path.join(IMAGE_DIR, filename)

    if not os.path.exists(image_path):
        return redirect(url_for('index'))

    metadata = extract_metadata_from_filename(filename)

    # Get file stats
    stats = os.stat(image_path)
    file_size = stats.st_size / (1024 * 1024)  # Convert to MB

    image_data = {
        "filename": filename,
        "timestamp": metadata["timestamp"],
        "exposure_ms": metadata["exposure_ms"],
        "size_mb": round(file_size, 2),
        "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    }

    return render_template('image_detail.html', image=image_data)


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
    return send_from_directory(IMAGE_DIR, filename)


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
    global background_capture_enabled

    # Use the persistent flag instead of just thread status
    # This ensures status is consistent even across restarts
    return jsonify({
        "is_capturing": is_capturing,
        "log": capture_log,
        "background_running": background_capture_enabled,
        "capture_interval": capture_interval
    })


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

            # Extract the day from the image timestamp
            if image['timestamp']:
                image_day = image['timestamp'].split(' ')[0]
            else:
                image_day = 'Unknown Date'

            # If this image's day is in the deletion list, mark it for deletion
            if image_day in days_to_delete:
                images_to_delete.append(image)
                if image_day not in deleted_days:
                    deleted_days.append(image_day)

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
        app.logger.info("System restart requested")

        # Stop background capture before restart
        global stop_capture_flag
        stop_capture_flag.set()

        # Platform-specific restart commands
        if platform.system() == "Linux":
            subprocess.Popen(["sudo", "reboot"])
        elif platform.system() == "Windows":
            subprocess.Popen(["shutdown", "/r", "/t", "5"])
        else:
            return jsonify({"status": "error", "message": "Unsupported platform"}), 400

        return jsonify({"status": "success", "message": "System restart initiated"})
    except Exception as e:
        app.logger.error(f"Error restarting system: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/system/shutdown', methods=['POST'])
def system_shutdown():
    """Shutdown the system."""
    try:
        app.logger.info("System shutdown requested")

        # Stop background capture before shutdown
        global stop_capture_flag
        stop_capture_flag.set()

        # Platform-specific shutdown commands
        if platform.system() == "Linux":
            subprocess.Popen(["sudo", "poweroff"])
        elif platform.system() == "Windows":
            subprocess.Popen(["shutdown", "/s", "/t", "5"])
        else:
            return jsonify({"status": "error", "message": "Unsupported platform"}), 400

        return jsonify({"status": "success", "message": "System shutdown initiated"})
    except Exception as e:
        app.logger.error(f"Error shutting down system: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


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


if __name__ == '__main__':
    # Load configuration from file
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

    app.run(host='0.0.0.0', port=5000, debug=False)
