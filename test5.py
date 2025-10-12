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
from datetime import datetime
from PIL import ImageDraw, ImageFont

# Configuration
OUTPUT_DIR = "./zwo_images"  # Directory to save images
GAIN = 50  # Camera gain (0-600, adjust based on your needs)
BRIGHTNESS = 50  # Brightness setting
TARGET_ADU = None  # Will be set to 1/4 of full-well capacity
TEST_REGION_SIZE = 200  # Size of central test region (200x200 pixels)
INITIAL_EXPOSURE_MS = 100  # Starting exposure for test shots
MAX_EXPOSURE_MS = 30000  # Maximum exposure time (30 seconds)
MIN_EXPOSURE_MS = 1  # Minimum exposure time

# Path to ZWO ASI SDK library
ASI_LIB_PATH = '/usr/local/lib/libASICamera2.so'


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
    
    target_adu = full_well / 4.0
    print(f"Image mode: 8-bit (RAW8)")
    print(f"Full-well capacity: {full_well} ADU")
    print(f"Target brightness: {target_adu:.1f} ADU (25% of full-well)")
    
    return camera, camera_info, target_adu, image_type, dtype


def configure_camera(camera, exposure_time_ms, image_type=asi.ASI_IMG_RAW8):
    """Configure camera settings"""
    # Set image type
    camera.set_image_type(image_type)
    
    # Set ROI (Region of Interest) - use full frame
    camera.set_roi(start_x=0, start_y=0)
    
    # Set control values (ensure integers)
    camera.set_control_value(asi.ASI_GAIN, int(GAIN), auto=False)
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


def capture_test_image(camera, camera_info, exposure_time_ms, dtype):
    """Capture a test image and return the data"""
    import time
    
    # Start exposure
    camera.start_exposure()
    
    # Wait for exposure to complete
    timeout = (exposure_time_ms / 1000.0) + 5
    start_time = time.time()
    
    while True:
        status = camera.get_exposure_status()
        if status == asi.ASI_EXP_SUCCESS:
            break
        elif status == asi.ASI_EXP_FAILED:
            return None
        
        if time.time() - start_time > timeout:
            return None
        
        time.sleep(0.01)
    
    # Get image data
    img_data = camera.get_data_after_exposure()
    
    # Convert to numpy array with correct dtype
    width = camera_info['MaxWidth']
    height = camera_info['MaxHeight']
    img_array = np.frombuffer(img_data, dtype=dtype)
    img_array = img_array.reshape((height, width))
    
    return img_array


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
    """Find optimal exposure time to reach target brightness"""
    print("\n" + "="*60)
    print("FINDING OPTIMAL EXPOSURE TIME")
    print("="*60)
    
    exposure_time_ms = INITIAL_EXPOSURE_MS
    max_iterations = 10
    tolerance = 0.05  # 5% tolerance
    
    for iteration in range(max_iterations):
        print(f"\nIteration {iteration + 1}:")
        print(f"  Testing exposure: {exposure_time_ms:.1f} ms")
        
        # Configure camera with test exposure
        configure_camera(camera, exposure_time_ms, image_type)
        
        # Capture test image
        img_array = capture_test_image(camera, camera_info, exposure_time_ms, dtype)
        
        if img_array is None:
            print("  Failed to capture test image!")
            return None
        
        # Calculate mean of central region
        mean_adu = get_central_region_mean(img_array, TEST_REGION_SIZE)
        print(f"  Central region mean: {mean_adu:.1f} ADU")
        print(f"  Target: {target_adu:.1f} ADU")
        
        # Check if we're within tolerance
        ratio = mean_adu / target_adu
        print(f"  Ratio: {ratio:.3f}")
        
        if abs(ratio - 1.0) < tolerance:
            print(f"\n✓ Optimal exposure found: {exposure_time_ms:.1f} ms")
            return exposure_time_ms
        
        # Adjust exposure time based on ratio
        # If too dark (ratio < 1), increase exposure
        # If too bright (ratio > 1), decrease exposure
        adjustment_factor = target_adu / mean_adu
        new_exposure = exposure_time_ms * adjustment_factor
        
        # Apply limits and convert to int
        new_exposure = int(max(MIN_EXPOSURE_MS, min(MAX_EXPOSURE_MS, new_exposure)))
        
        # Check if we're stuck (exposure not changing significantly)
        if abs(new_exposure - exposure_time_ms) < 1:
            print(f"\n✓ Converged to exposure: {exposure_time_ms:.1f} ms")
            return exposure_time_ms
        
        exposure_time_ms = new_exposure
        
        # Check if we hit limits
        if exposure_time_ms >= MAX_EXPOSURE_MS:
            print(f"\n⚠ Hit maximum exposure limit: {MAX_EXPOSURE_MS} ms")
            return MAX_EXPOSURE_MS
        elif exposure_time_ms <= MIN_EXPOSURE_MS:
            print(f"\n⚠ Hit minimum exposure limit: {MIN_EXPOSURE_MS} ms")
            return MIN_EXPOSURE_MS
    
    print(f"\n⚠ Max iterations reached. Using: {exposure_time_ms:.1f} ms")
    return exposure_time_ms


def capture_final_image(camera, camera_info, output_dir, exposure_time_ms, image_type, dtype):
    """Capture final full-resolution image"""
    print("\n" + "=" * 60)
    print("CAPTURING FINAL IMAGE")
    print("=" * 60)

    # Configure camera with optimal exposure
    configure_camera(camera, exposure_time_ms, image_type)

    print(f"\nCapturing final image with {exposure_time_ms:.1f} ms exposure...")

    # Capture image
    img_array = capture_test_image(camera, camera_info, exposure_time_ms, dtype)

    if img_array is None:
        print("Failed to capture final image!")
        return None

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"zwo_optimal_{timestamp}_exp{exposure_time_ms:.0f}ms.png"
    filepath = os.path.join(output_dir, filename)

    # Save image
    img = Image.fromarray(img_array)

    # Add timestamp to the bottom left corner in white
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Convert to RGB mode if it's not already
    if img.mode != "RGB":
        img = img.convert("RGB")

    draw = ImageDraw.Draw(img)

    # Try to use a default font
    try:
        # Try to get a font - adjust size as needed
        font = ImageFont.truetype("arial.ttf", 24)  # Adjust size as needed
    except IOError:
        # Use default font if custom font not available
        font = ImageFont.load_default()

    # Draw the text in white at the bottom left
    draw.text((10, img.height - 40), current_time, fill=(255, 255, 255), font=font)

    # Save the modified image
    img.save(filepath)

    width, height = img_array.shape[1], img_array.shape[0]
    mean_brightness = np.mean(img_array)

    print(f"\n✓ Image saved to: {filepath}")
    print(f"  Resolution: {width}x{height}")
    print(f"  Mean brightness: {mean_brightness:.1f} ADU")
    print(f"  Exposure time: {exposure_time_ms:.1f} ms")

    return filepath


def main():
    """Main function"""
    camera = None
    try:
        # Initialize camera
        camera, camera_info, target_adu, image_type, dtype = initialize_camera()
        
        # Find optimal exposure time
        optimal_exposure = find_optimal_exposure(camera, camera_info, target_adu, image_type, dtype)
        
        if optimal_exposure is None:
            print("\nFailed to find optimal exposure!")
            if camera:
                try:
                    camera.close()
                except:
                    pass
            sys.exit(1)
        
        # Capture final image with optimal exposure
        filepath = capture_final_image(camera, camera_info, OUTPUT_DIR, optimal_exposure, image_type, dtype)
        
        if filepath:
            print("\n" + "="*60)
            print("SUCCESS!")
            print("="*60)
        else:
            print("\nFinal capture failed!")
            if camera:
                try:
                    camera.close()
                except:
                    pass
            sys.exit(1)
        
        # Close camera properly
        if camera:
            try:
                camera.close()
                del camera  # Explicitly delete the camera object
            except:
                pass
        
        return True
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        if camera:
            try:
                camera.close()
            except:
                pass
        sys.exit(0)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        if camera:
            try:
                camera.close()
            except:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
