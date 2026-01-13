#!/usr/bin/env python3
"""
ZWO ASI Camera Auto-Exposure Image Capture Script
Automatically finds optimal exposure time to reach target brightness
Compatible with Ubuntu 22.04
"""

import zwoasi as asi
import numpy as np
from PIL import Image
import os
import sys
import json
import math
from datetime import datetime
from PIL import ImageDraw, ImageFont

# Configuration
OUTPUT_DIR = os.path.expanduser("~/allsky_images")  # Directory to save images (dynamic path)
GAIN = 50  # Default camera gain (0-600, adjust based on your needs)
BRIGHTNESS = 50  # Brightness setting
TARGET_ADU = None  # Will be set to 1/4 of full-well capacity
TEST_REGION_SIZE = 400  # Size of central test region (400x400 pixels - increased from 200x200)
INITIAL_EXPOSURE_MS = 100  # Starting exposure for test shots
MAX_EXPOSURE_MS = 30000  # Maximum exposure time (30 seconds) - can be overridden by config
MIN_EXPOSURE_MS = 0.034  # Minimum exposure time (34 microseconds) - can be overridden by config
FALLBACK_EXPOSURE_MS = 30000  # Fallback exposure if auto-exposure fails completely

# Adaptive Gain Configuration
MIN_GAIN = 0  # Minimum camera gain (used for daytime)
MAX_GAIN = 200  # Maximum camera gain to try during search
GAIN_INCREMENT = 50  # Gain increment steps (0, 50, 100, 150, 200)
DAYTIME_GAIN = 0  # Gain for daytime/civil twilight
NAUTICAL_GAIN = 50  # Gain for nautical twilight
NIGHT_GAIN = 100  # Gain for astronomical darkness

# Path to ZWO ASI SDK library
ASI_LIB_PATH = '/usr/local/lib/libASICamera2.so'


def load_exposure_config():
    """Load min/max exposure settings from config file"""
    global MIN_EXPOSURE_MS, MAX_EXPOSURE_MS, FALLBACK_EXPOSURE_MS

    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_config.json")

    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)

                if 'min_exposure_ms' in config:
                    MIN_EXPOSURE_MS = max(0.034, float(config['min_exposure_ms']))
                    print(f"Loaded min exposure: {MIN_EXPOSURE_MS} ms")

                if 'max_exposure_ms' in config:
                    MAX_EXPOSURE_MS = max(100, int(config['max_exposure_ms']))
                    print(f"Loaded max exposure: {MAX_EXPOSURE_MS} ms")

                # Set fallback to max exposure
                FALLBACK_EXPOSURE_MS = MAX_EXPOSURE_MS
    except Exception as e:
        print(f"Warning: Could not load exposure config: {e}")
        print(f"Using default values: min={MIN_EXPOSURE_MS}ms, max={MAX_EXPOSURE_MS}ms")


def get_solar_period():
    """Determine current solar period (daytime, civil_twilight, nautical_twilight, astronomical_darkness)"""
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_config.json")

    try:
        if not os.path.exists(config_file):
            return 'unknown'

        with open(config_file, 'r') as f:
            config = json.load(f)

        settings = config.get('settings', {})
        lat = settings.get('latitude')
        lon = settings.get('longitude')

        if lat is None or lon is None:
            return 'unknown'

        now = datetime.now()

        def calculate_solar_noon(lon):
            return 12.0 - (lon / 15.0)

        def calculate_sunrise_sunset(lat, lon, date):
            day_of_year = date.timetuple().tm_yday
            declination = 23.45 * math.sin(math.radians((360/365) * (day_of_year - 81)))
            lat_rad = math.radians(lat)
            dec_rad = math.radians(declination)
            cos_hour_angle = -math.tan(lat_rad) * math.tan(dec_rad)

            if cos_hour_angle < -1 or cos_hour_angle > 1:
                return None, None

            hour_angle = math.degrees(math.acos(cos_hour_angle))
            solar_noon = calculate_solar_noon(lon)
            sunrise_hour = solar_noon - (hour_angle / 15.0)
            sunset_hour = solar_noon + (hour_angle / 15.0)

            tz_offset = settings.get('timezone', 0) or 0
            if settings.get('dst_enabled'):
                tz_offset += 1

            sunrise_hour += tz_offset
            sunset_hour += tz_offset

            return sunrise_hour, sunset_hour

        sunrise_hour, sunset_hour = calculate_sunrise_sunset(lat, lon, now)

        if sunrise_hour is None or sunset_hour is None:
            return 'unknown'

        # Calculate twilight times
        civil_twilight_end = (sunset_hour + 0.5) % 24
        nautical_twilight_end = (sunset_hour + 1.0) % 24
        astronomical_twilight_end = (sunset_hour + 1.5) % 24
        astronomical_twilight_begin = (sunrise_hour - 1.5) % 24
        nautical_twilight_begin = (sunrise_hour - 1.0) % 24
        civil_twilight_begin = (sunrise_hour - 0.5) % 24

        current_hour = now.hour + now.minute / 60

        # Check astronomical darkness
        if astronomical_twilight_end < astronomical_twilight_begin:
            if current_hour >= astronomical_twilight_end and current_hour < astronomical_twilight_begin:
                return 'astronomical_darkness'
        else:
            if current_hour >= astronomical_twilight_end or current_hour < astronomical_twilight_begin:
                return 'astronomical_darkness'

        # Check nautical twilight
        if sunset_hour <= current_hour < astronomical_twilight_end or astronomical_twilight_begin <= current_hour < sunrise_hour:
            return 'nautical_twilight'

        # Check civil twilight
        if (sunset_hour - 0.5) <= current_hour < sunset_hour or sunrise_hour <= current_hour < (sunrise_hour + 0.5):
            return 'civil_twilight'

        return 'daytime'

    except Exception as e:
        print(f"Warning: Could not determine solar period: {e}")
        return 'unknown'


def get_initial_gain():
    """Determine initial camera gain based on solar period"""
    period = get_solar_period()

    if period in ['daytime', 'civil_twilight']:
        print(f"Solar period: {period} - Using daytime gain ({DAYTIME_GAIN})")
        return DAYTIME_GAIN
    elif period == 'nautical_twilight':
        print(f"Solar period: {period} - Using nautical gain ({NAUTICAL_GAIN})")
        return NAUTICAL_GAIN
    elif period == 'astronomical_darkness':
        print(f"Solar period: {period} - Using night gain ({NIGHT_GAIN})")
        return NIGHT_GAIN
    else:
        print(f"Solar period: unknown - Using nautical gain ({NAUTICAL_GAIN})")
        return NAUTICAL_GAIN


def initialize_camera():
    """Initialize the ZWO ASI camera"""
    # Set library path
    asi.init(ASI_LIB_PATH)
    
    # Get number of connected cameras
    num_cameras = asi.get_num_cameras()
    if num_cameras == 0:
        print("No ZWO cameras detected!")
        sys.exit(1)
    
    print(f"Found {num_cameras} camera(s)")
    
    # Get camera properties
    cameras_found = asi.list_cameras()
    print("Available cameras:")
    for i, camera_name in enumerate(cameras_found):
        print(f"  {i}: {camera_name}")
    
    # Open the first camera
    camera = asi.Camera(0)
    camera_info = camera.get_camera_property()
    
    print(f"\nConnected to: {camera_info['Name']}")
    print(f"Resolution: {camera_info['MaxWidth']}x{camera_info['MaxHeight']}")
    print(f"Bit Depth: {camera_info['BitDepth']}")
    
    # We're using 8-bit mode (ASI_IMG_RAW8) so target should be based on 8-bit range
    # Even if the camera has higher bit depth, we need to match the image type we're using
    full_well = 255  # Using 8-bit image type
    image_type = asi.ASI_IMG_RAW8
    dtype = np.uint8
    
    target_adu = TARGET_ADU #full_well / 4.0
    print(f"Image mode: 8-bit (RAW8)")
    print(f"Full-well capacity: {full_well} ADU")
    print(f"Target brightness: {target_adu:.1f} ADU (25% of full-well)")
    
    return camera, camera_info, target_adu, image_type, dtype


def configure_camera(camera, exposure_time_ms, image_type=asi.ASI_IMG_RAW8, gain=None):
    """Configure camera settings"""
    # Set image type
    camera.set_image_type(image_type)

    # Set ROI (Region of Interest) - use full frame
    camera.set_roi(start_x=0, start_y=0)

    # Use provided gain or default GAIN
    if gain is None:
        gain = GAIN

    # Set control values (ensure integers)
    camera.set_control_value(asi.ASI_GAIN, int(gain), auto=False)
    camera.set_control_value(asi.ASI_EXPOSURE, int(exposure_time_ms * 1000), auto=False)
    camera.set_control_value(asi.ASI_BRIGHTNESS, int(BRIGHTNESS))
    
    # Set white balance (for color cameras)
    try:
        camera.set_control_value(asi.ASI_WB_B, 95)
        camera.set_control_value(asi.ASI_WB_R, 52)
    except:
        pass  # Mono cameras don't have white balance
    
    # Set bandwidth overload
    try:
        camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, 40)
    except:
        pass
    
    # Set high speed mode
    try:
        camera.set_control_value(asi.ASI_HIGH_SPEED_MODE, 0)
    except:
        pass


def capture_test_image(camera, camera_info, exposure_time_ms, dtype, retries=3):
    """Capture a test image and return the data"""
    import time

    for attempt in range(retries):
        try:
            # Start exposure
            camera.start_exposure()

            # Wait for exposure to complete
            timeout = (exposure_time_ms / 1000.0) + 10  # Increased timeout buffer
            start_time = time.time()

            while True:
                status = camera.get_exposure_status()
                if status == asi.ASI_EXP_SUCCESS:
                    break
                elif status == asi.ASI_EXP_FAILED:
                    if attempt < retries - 1:
                        print(f"    Exposure failed, retrying (attempt {attempt + 2}/{retries})...")
                        time.sleep(0.5)
                        break
                    return None

                if time.time() - start_time > timeout:
                    if attempt < retries - 1:
                        print(f"    Timeout, retrying (attempt {attempt + 2}/{retries})...")
                        time.sleep(0.5)
                        break
                    return None

                time.sleep(0.01)

            # Only get data if exposure succeeded
            if status == asi.ASI_EXP_SUCCESS:
                # Get image data
                img_data = camera.get_data_after_exposure()

                # Convert to numpy array with correct dtype
                width = camera_info['MaxWidth']
                height = camera_info['MaxHeight']
                img_array = np.frombuffer(img_data, dtype=dtype)
                img_array = img_array.reshape((height, width))

                return img_array

        except Exception as e:
            if attempt < retries - 1:
                print(f"    Capture error: {e}, retrying (attempt {attempt + 2}/{retries})...")
                time.sleep(0.5)
            else:
                print(f"    Capture error: {e}")
                return None

    return None


def get_central_region_mean(img_array, region_size=200):
    """Calculate mean value of central region"""
    height, width = img_array.shape
    center_y = height // 2
    center_x = width // 2
    half_region = region_size // 2
    
    # Extract central region
    y_start = max(0, center_y - half_region)
    y_end = min(height, center_y + half_region)
    x_start = max(0, center_x - half_region)
    x_end = min(width, center_x + half_region)
    
    central_region = img_array[y_start:y_end, x_start:x_end]
    mean_value = np.mean(central_region)
    
    return mean_value


def find_optimal_exposure(camera, camera_info, target_adu, image_type, dtype):
    """
    Find optimal exposure time to reach target brightness using adaptive gain and smart search.

    This improved algorithm:
    - Uses adaptive gain based on time of day (0 for daytime, higher for night)
    - Increments gain when max exposure is reached but still too dark
    - Tests initial exposure steps to find bounds (too dark / too bright)
    - Refines search between bounds using smaller steps
    - Stops searching when image is too bright (no need to test longer exposures)
    - Logs all attempts and failures for debugging
    """
    print("\n" + "="*60, flush=True)
    print("FINDING OPTIMAL EXPOSURE TIME (ADAPTIVE GAIN SEARCH)", flush=True)
    print("="*60, flush=True)
    print(f"Min exposure: {MIN_EXPOSURE_MS} ms", flush=True)
    print(f"Max exposure: {MAX_EXPOSURE_MS} ms", flush=True)
    print(f"Target brightness: {target_adu:.1f} ADU", flush=True)
    print(f"Test region size: {TEST_REGION_SIZE}x{TEST_REGION_SIZE} pixels", flush=True)

    # Determine initial gain based on solar period
    initial_gain = get_initial_gain()
    current_gain = initial_gain

    tolerance = 0.15  # Accept images within 15% of target
    best_exposure = None
    best_gain = None
    best_mean_adu = None
    best_ratio_diff = float('inf')

    failed_captures = []  # Track all failures
    successful_captures = []  # Track all successes

    # Helper function to test an exposure with current gain
    def test_exposure(exposure_time_ms, gain):
        nonlocal best_exposure, best_gain, best_mean_adu, best_ratio_diff

        print(f"\nTesting exposure: {exposure_time_ms:.3f} ms @ gain {gain}", flush=True)

        # Configure camera with test exposure and current gain
        try:
            configure_camera(camera, exposure_time_ms, image_type, gain=gain)
        except Exception as e:
            error_msg = f"Failed to configure camera: {e}"
            print(f"  ✗ {error_msg}", flush=True)
            failed_captures.append({
                'exposure_ms': exposure_time_ms,
                'error': error_msg,
                'type': 'configuration_error'
            })
            return None

        # Capture test image with retries
        img_array = capture_test_image(camera, camera_info, exposure_time_ms, dtype, retries=3)

        if img_array is None:
            error_msg = "Failed to capture image after 3 retries"
            print(f"  ✗ {error_msg}", flush=True)
            failed_captures.append({
                'exposure_ms': exposure_time_ms,
                'error': error_msg,
                'type': 'capture_failed'
            })
            return None

        # Calculate mean of central region
        try:
            mean_adu = get_central_region_mean(img_array, TEST_REGION_SIZE)
        except Exception as e:
            error_msg = f"Failed to calculate brightness: {e}"
            print(f"  ✗ {error_msg}", flush=True)
            failed_captures.append({
                'exposure_ms': exposure_time_ms,
                'error': error_msg,
                'type': 'calculation_error'
            })
            return None

        ratio = mean_adu / target_adu
        ratio_diff = abs(ratio - 1.0)

        print(f"  ✓ Mean brightness: {mean_adu:.1f} ADU (target: {target_adu:.1f})", flush=True)
        print(f"  ✓ Ratio: {ratio:.3f} (difference: {ratio_diff:.3f})", flush=True)

        # Record successful capture
        successful_captures.append({
            'exposure_ms': exposure_time_ms,
            'mean_adu': mean_adu,
            'ratio': ratio,
            'ratio_diff': ratio_diff
        })

        # Update best result
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_exposure = exposure_time_ms
            best_gain = gain
            best_mean_adu = mean_adu
            print(f"  → New best: {best_exposure:.3f} ms @ gain {best_gain} (ratio diff: {best_ratio_diff:.3f})", flush=True)

        return mean_adu

    # PHASE 1: Find bounds using coarse steps with adaptive gain
    print("\n--- PHASE 1: Finding bounds with adaptive gain ---", flush=True)
    coarse_steps = [0.034, 0.05, 0.1, 0.2, 0.5, 1, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 30000]
    coarse_steps = [e for e in coarse_steps if MIN_EXPOSURE_MS <= e <= MAX_EXPOSURE_MS]

    lower_bound = None  # Exposure that's too dark
    upper_bound = None  # Exposure that's too bright
    found_optimal = False

    # For each exposure time, try increasing gain levels before moving to next exposure
    for exposure_ms in coarse_steps:
        print(f"\n--- Testing exposure: {exposure_ms:.3f} ms ---", flush=True)

        # Try different gain levels at this exposure time
        for current_gain in range(initial_gain, MAX_GAIN + 1, GAIN_INCREMENT):
            mean_adu = test_exposure(exposure_ms, current_gain)

            if mean_adu is None:
                continue

            ratio_diff = abs(mean_adu / target_adu - 1.0)

            # Found good exposure?
            if ratio_diff < tolerance:
                print(f"\n✓ ✓ ✓ OPTIMAL EXPOSURE FOUND: {exposure_ms:.3f} ms @ gain {current_gain} ✓ ✓ ✓", flush=True)
                print(f"  Final brightness: {mean_adu:.1f} ADU (target: {target_adu:.1f})", flush=True)
                print_capture_summary(successful_captures, failed_captures)
                sys.stdout.flush()
                return exposure_ms, current_gain

            # Check if too bright or too dark
            if mean_adu > target_adu:
                # Too bright - no need to try higher gain at this exposure
                if lower_bound is None:
                    # First exposure is too bright - we're done
                    upper_bound = exposure_ms
                    print(f"  → Image too bright at {exposure_ms:.3f} ms @ gain {current_gain} - stopping search", flush=True)
                    found_optimal = True
                    break
                else:
                    # We have bounds - proceed to refinement
                    upper_bound = exposure_ms
                    print(f"  → Too bright - setting upper bound to {exposure_ms:.3f} ms", flush=True)
                    found_optimal = True
                    break
            else:
                # Too dark
                if current_gain < MAX_GAIN:
                    print(f"  → Too dark @ gain {current_gain}, trying higher gain...", flush=True)
                    continue  # Try next gain level
                else:
                    # Max gain reached and still too dark
                    lower_bound = exposure_ms
                    print(f"  → Too dark even @ gain {current_gain}, need longer exposure", flush=True)
                    break  # Move to next exposure time

        # If we found bounds, stop coarse search
        if found_optimal or (lower_bound is not None and upper_bound is not None):
            break

    # PHASE 2: Refine search between bounds
    if lower_bound is not None and upper_bound is not None:
        print(f"\n--- PHASE 2: Refining search between {lower_bound} and {upper_bound} ms ---", flush=True)

        # Generate refinement steps between bounds
        diff = upper_bound - lower_bound

        if diff > 100:
            step_size = min(10, diff // 10)
            refine_steps = list(range(int(lower_bound), int(upper_bound), int(step_size)))
        elif diff > 10:
            refine_steps = list(range(int(lower_bound), int(upper_bound), 1))
        else:
            refine_steps = [lower_bound + i * 0.5 for i in range(1, int(diff * 2))]

        # Test refinement steps with adaptive gain
        for exposure_ms in refine_steps:
            if exposure_ms <= lower_bound or exposure_ms >= upper_bound:
                continue

            # Try increasing gain at each refinement exposure
            for current_gain in range(initial_gain, MAX_GAIN + 1, GAIN_INCREMENT):
                mean_adu = test_exposure(exposure_ms, current_gain)

                if mean_adu is None:
                    continue

                ratio_diff = abs(mean_adu / target_adu - 1.0)

                # Found good exposure?
                if ratio_diff < tolerance:
                    print(f"\n✓ ✓ ✓ OPTIMAL EXPOSURE FOUND: {exposure_ms:.3f} ms @ gain {current_gain} ✓ ✓ ✓", flush=True)
                    print(f"  Final brightness: {mean_adu:.1f} ADU (target: {target_adu:.1f})", flush=True)
                    print_capture_summary(successful_captures, failed_captures)
                    sys.stdout.flush()
                    return exposure_ms, current_gain

                # If too bright, no need to try higher gain
                if mean_adu > target_adu:
                    break

                # If too dark and not at max gain, try higher gain
                if current_gain < MAX_GAIN:
                    continue
                else:
                    break  # Max gain reached, move to next exposure

    # Use the best result we found
    print("\n" + "="*60, flush=True)
    print("EXPOSURE SEARCH COMPLETE", flush=True)
    print("="*60, flush=True)
    print_capture_summary(successful_captures, failed_captures)

    if best_exposure is not None:
        print(f"\n✓ Using best exposure found: {best_exposure:.3f} ms @ gain {best_gain}", flush=True)
        print(f"  Brightness: {best_mean_adu:.1f} ADU (target: {target_adu:.1f})", flush=True)
        print(f"  Ratio difference: {best_ratio_diff:.3f}", flush=True)
        return best_exposure, best_gain

    # If everything failed, use fallback
    print(f"\n⚠ ⚠ ⚠ ALL EXPOSURES FAILED - USING FALLBACK: {FALLBACK_EXPOSURE_MS} ms @ gain {initial_gain} ⚠ ⚠ ⚠", flush=True)
    return FALLBACK_EXPOSURE_MS, initial_gain


def print_capture_summary(successful_captures, failed_captures):
    """Print a summary of all capture attempts"""
    print(f"\nCapture Summary:")
    print(f"  Successful: {len(successful_captures)}")
    print(f"  Failed: {len(failed_captures)}")

    if failed_captures:
        print(f"\nFailed Captures:")
        for failure in failed_captures:
            print(f"  - {failure['exposure_ms']}ms: {failure['error']} ({failure['type']})")

    if successful_captures:
        print(f"\nSuccessful Captures:")
        for capture in successful_captures:
            print(f"  - {capture['exposure_ms']}ms: {capture['mean_adu']:.1f} ADU (ratio: {capture['ratio']:.3f})")


def capture_final_image(camera, camera_info, output_dir, exposure_time_ms, gain, image_type, dtype):
    """Capture final full-resolution image"""
    print("\n" + "=" * 60)
    print("CAPTURING FINAL IMAGE")
    print("=" * 60)

    # Configure camera with optimal exposure and gain
    configure_camera(camera, exposure_time_ms, image_type, gain=gain)

    print(f"\nCapturing final image with {exposure_time_ms:.3f} ms exposure @ gain {gain}...")

    # Capture image
    img_array = capture_test_image(camera, camera_info, exposure_time_ms, dtype)

    if img_array is None:
        print("Failed to capture final image!")
        return None

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Format exposure time for filename (use microseconds if < 1ms)
    if exposure_time_ms < 1:
        exp_str = f"{int(exposure_time_ms * 1000)}us"
    else:
        exp_str = f"{exposure_time_ms:.0f}ms"
    filename = f"{timestamp}_exp{exp_str}.png"
    filepath = os.path.join(output_dir, filename)

    # Save image
    img = Image.fromarray(img_array)
    img.save(filepath)

    width, height = img_array.shape[1], img_array.shape[0]
    mean_brightness = np.mean(img_array)

    print(f"\n✓ Image saved to: {filepath}")
    print(f"  Resolution: {width}x{height}")
    print(f"  Mean brightness: {mean_brightness:.1f} ADU")
    print(f"  Exposure time: {exposure_time_ms:.3f} ms")

    return filepath


def close_camera_safely(camera):
    """Safely close camera with proper error handling"""
    if camera is None:
        return

    try:
        # Try to stop any ongoing exposure
        try:
            camera.stop_exposure()
        except:
            pass

        # Close the camera
        camera.close()
        print("Camera closed successfully")
    except Exception as e:
        print(f"Warning during camera cleanup: {e}")
        # Don't raise, just warn


def main():
    """Main function"""
    camera = None
    try:
        # Load exposure configuration from app_config.json
        load_exposure_config()

        # Initialize camera
        camera, camera_info, target_adu, image_type, dtype = initialize_camera()

        # Find optimal exposure time and gain
        optimal_exposure, optimal_gain = find_optimal_exposure(camera, camera_info, target_adu, image_type, dtype)

        if optimal_exposure is None:
            print("\n⚠ Failed to find optimal exposure! Using default 1000ms @ gain 50.")
            optimal_exposure = 1000  # Use 1 second as fallback
            optimal_gain = 50

        # Capture final image with optimal exposure and gain
        filepath = capture_final_image(camera, camera_info, OUTPUT_DIR, optimal_exposure, optimal_gain, image_type, dtype)

        if filepath:
            print("\n" + "="*60)
            print("SUCCESS!")
            print("="*60)
            close_camera_safely(camera)
            return True
        else:
            print("\n⚠ Final capture failed! Trying one more time with fallback settings...")

            # Try one more time with a safe exposure setting
            fallback_exposure = 1000
            fallback_gain = 50
            filepath = capture_final_image(camera, camera_info, OUTPUT_DIR, fallback_exposure, fallback_gain, image_type, dtype)

            if filepath:
                print("\n✓ Fallback capture succeeded!")
                close_camera_safely(camera)
                return True
            else:
                print("\n✗ All capture attempts failed!")
                close_camera_safely(camera)
                sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        close_camera_safely(camera)
        sys.exit(0)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        close_camera_safely(camera)
        sys.exit(1)


if __name__ == "__main__":
    main()
