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

app = Flask(__name__)

# Configure this to match your output directory
IMAGE_DIR = "/home/kickpi/zwo_images/zwo_images"
SCRIPT_PATH = "/home/kickpi/zwo_images/test5.py"  # Path to your capture script

# Global variables to track capture process
capture_interval = 300  # Default 5 minutes
is_capturing = False
capture_log = []
capture_thread = None
stop_capture_flag = False
last_capture_time = None


def extract_metadata_from_filename(filename):
    """Extract metadata from the ZWO image filename"""
    metadata = {
        "timestamp": None,
        "exposure_ms": None
    }

    # Extract timestamp (format: zwo_optimal_YYYYMMDD_HHMMSS_expXXXms.png)
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
    image_pattern = os.path.join(IMAGE_DIR, "zwo_optimal_*.png")
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
    global capture_thread, stop_capture_flag
    
    if capture_thread and capture_thread.is_alive():
        return False, "Background capture already running"
    
    stop_capture_flag = False
    capture_thread = threading.Thread(target=background_capture_loop, daemon=True)
    capture_thread.start()
    
    return True, "Background capture started"


def stop_background_capture():
    """Stop the background capture thread"""
    global stop_capture_flag, capture_thread
    
    if not capture_thread or not capture_thread.is_alive():
        return False, "Background capture not running"
    
    stop_capture_flag = True
    capture_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] Stopping background capture...")
    
    # Wait for thread to finish (with timeout)
    capture_thread.join(timeout=5)
    
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
                           background_running=capture_thread and capture_thread.is_alive())


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
                           background_running=capture_thread and capture_thread.is_alive(),
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
    return jsonify({
        "is_capturing": is_capturing,
        "log": capture_log,
        "background_running": capture_thread and capture_thread.is_alive(),
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
    global capture_interval
    
    try:
        new_interval = int(request.form.get('interval', 300))
        if new_interval < 30:
            return jsonify({"status": "error", "message": "Interval must be at least 30 seconds"})
        
        capture_interval = new_interval
        
        # If background capture is running, restart it with new interval
        if capture_thread and capture_thread.is_alive():
            stop_background_capture()
            time.sleep(1)
            start_background_capture()
            message = f"Capture interval updated to {capture_interval} seconds and restarted"
        else:
            message = f"Capture interval updated to {capture_interval} seconds"
        
        return jsonify({"status": "success", "message": message})
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid interval value"})


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


if __name__ == '__main__':
    # Start background capture automatically on startup
    start_background_capture()
    
    app.run(host='0.0.0.0', port=5000, debug=False)
