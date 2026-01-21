#!/usr/bin/env python3
"""
Generate extended star catalog from HYG database (Hipparcos Yale Gliese)
This script downloads and processes the HYG database to create a star catalog
with stars up to magnitude 7.
"""

import json
import urllib.request
import csv
import io
import gzip

def download_hyg_catalog():
    """Download HYG database from astronexus.com"""
    # Try multiple URLs - some are compressed
    urls = [
        ("https://www.astronexus.com/downloads/catalogs/hygdata_v42.csv.gz", True),
        ("https://www.astronexus.com/downloads/catalogs/hygdata_v37.csv.gz", True),
    ]

    for url, is_gzipped in urls:
        print(f"Trying {url}...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=120) as response:
                raw_data = response.read()
                print(f"Downloaded {len(raw_data)} bytes")

                if is_gzipped:
                    data = gzip.decompress(raw_data).decode('utf-8')
                    print(f"Decompressed to {len(data)} bytes")
                else:
                    data = raw_data.decode('utf-8')

                return data
        except Exception as e:
            print(f"  Failed: {e}")
            continue

    return None
    print(f"Downloading HYG catalog from {url}...")

    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read().decode('utf-8')
            print(f"Downloaded {len(data)} bytes")
            return data
    except Exception as e:
        print(f"Error downloading: {e}")
        return None

def parse_hyg_catalog(csv_data, max_magnitude=7.0):
    """Parse HYG catalog and extract stars up to max_magnitude"""
    stars = []
    reader = csv.DictReader(io.StringIO(csv_data))

    for row in reader:
        try:
            mag = float(row.get('mag', 99))
            if mag > max_magnitude:
                continue

            # Skip the Sun
            proper_name = row.get('proper', '').strip()
            if proper_name == 'Sol':
                continue

            ra = float(row.get('ra', 0))  # Already in decimal hours
            dec = float(row.get('dec', 0))  # Already in decimal degrees

            # Get star name - prefer proper name, then Bayer designation
            proper_name = row.get('proper', '').strip()
            bayer = row.get('bayer', '').strip()
            constellation = row.get('con', '').strip()

            # Format Bayer designation nicely
            bayer_full = ''
            if bayer and constellation:
                bayer_full = f"{bayer} {constellation}"

            star = {
                "ra": round(ra, 4),
                "dec": round(dec, 4),
                "mag": round(mag, 2)
            }

            if proper_name:
                star["name"] = proper_name
            if bayer_full:
                star["bayer"] = bayer_full

            stars.append(star)

        except (ValueError, KeyError) as e:
            continue

    # Sort by magnitude (brightest first)
    stars.sort(key=lambda x: x['mag'])

    return stars

def main():
    # Download catalog
    csv_data = download_hyg_catalog()
    if not csv_data:
        print("Failed to download catalog")
        return

    # Parse stars up to magnitude 7
    print("Parsing catalog...")
    stars = parse_hyg_catalog(csv_data, max_magnitude=7.0)
    print(f"Found {len(stars)} stars with magnitude <= 7.0")

    # Count by magnitude
    mag_counts = {}
    for s in stars:
        mag_bin = int(s['mag']) if s['mag'] >= 0 else -1
        mag_counts[mag_bin] = mag_counts.get(mag_bin, 0) + 1

    print("\nStars by magnitude:")
    for mag in sorted(mag_counts.keys()):
        print(f"  Mag {mag} to {mag+1}: {mag_counts[mag]} stars")

    # Create catalog JSON
    catalog = {
        "description": "Extended Star Catalog - Stars with magnitude <= 7.0 from HYG Database (Hipparcos Yale Gliese)",
        "source": "HYG Database v3.7 - https://github.com/astronexus/HYG-Database",
        "epoch": "J2000",
        "coordinate_units": {
            "ra": "decimal hours (0-24)",
            "dec": "decimal degrees (-90 to +90)"
        },
        "total_stars": len(stars),
        "stars": stars
    }

    # Write to file
    output_path = "static/data/bright_stars.json"
    print(f"\nWriting {len(stars)} stars to {output_path}...")

    with open(output_path, 'w') as f:
        json.dump(catalog, f, indent=2)

    print("Done!")

if __name__ == "__main__":
    main()
