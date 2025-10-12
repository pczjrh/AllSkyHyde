#!/usr/bin/env python3
"""
ZWO ASI Camera Loop Capture Script
Repeatedly captures optimally exposed images
"""

import time
import sys
import warnings

# Suppress the zwoasi cleanup warning
warnings.filterwarnings('ignore', category=DeprecationWarning)

# Configuration
LOOP_COUNT = 0  # Number of images to capture (set to None for infinite loop)
DELAY_BETWEEN_CAPTURES = 300  # Seconds to wait between captures
RUN_CONTINUOUSLY = True  # Set to True for infinite loop

def run_capture():
    """Run a single capture cycle"""
    import subprocess
    
    # Run the main capture script
    result = subprocess.run(
        ['python3', 'test5.py'],
        capture_output=False,
        text=True
    )
    
    return result.returncode == 0


def main():
    """Main loop function"""
    capture_count = 0
    success_count = 0
    fail_count = 0
    
    print("="*60)
    print("ZWO CAMERA LOOP CAPTURE")
    print("="*60)
    
    if RUN_CONTINUOUSLY or LOOP_COUNT is None:
        print("Mode: Continuous (Ctrl+C to stop)")
    else:
        print(f"Mode: {LOOP_COUNT} captures")
    
    print(f"Delay between captures: {DELAY_BETWEEN_CAPTURES} seconds")
    print("="*60)
    print()
    
    try:
        while True:
            capture_count += 1
            
            if not RUN_CONTINUOUSLY and LOOP_COUNT is not None and capture_count > LOOP_COUNT:
                break
            
            print(f"\n{'='*60}")
            print(f"CAPTURE #{capture_count}")
            if not RUN_CONTINUOUSLY and LOOP_COUNT is not None:
                print(f"({capture_count}/{LOOP_COUNT})")
            print(f"{'='*60}\n")
            
            # Run capture
            success = run_capture()
            
            if success:
                success_count += 1
                print(f"\n✓ Capture #{capture_count} successful")
            else:
                fail_count += 1
                print(f"\n✗ Capture #{capture_count} failed")
            
            # Check if we should continue
            if not RUN_CONTINUOUSLY and LOOP_COUNT is not None and capture_count >= LOOP_COUNT:
                break
            
            # Wait before next capture
            print(f"\nWaiting {DELAY_BETWEEN_CAPTURES} seconds before next capture...")
            time.sleep(DELAY_BETWEEN_CAPTURES)
    
    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print("INTERRUPTED BY USER")
        print("="*60)
    
    finally:
        # Print summary
        print("\n" + "="*60)
        print("CAPTURE SUMMARY")
        print("="*60)
        print(f"Total captures attempted: {capture_count}")
        print(f"Successful: {success_count}")
        print(f"Failed: {fail_count}")
        print(f"Success rate: {(success_count/capture_count*100) if capture_count > 0 else 0:.1f}%")
        print("="*60)


if __name__ == "__main__":
    main()
