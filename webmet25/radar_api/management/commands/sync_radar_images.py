"""
Management command to scan product_output folder and sync PNG images to RadarImage model.

Scans /app/product_output/RADAR_CODE/YYYY/MM/DD/ for PNG files with naming convention:
  RADAR_CODE_YYYYMMDDTHHmmssZ_PRODUCT_VAR_SWEEP.png
  
Parses filenames, extracts metadata, and creates/updates RadarImage records.
Idempotent: only creates new records if not already in DB.
"""

import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from dateutil import parser
from radar_api.models import Radar, RadarImage


class Command(BaseCommand):
    help = "Sync PNG images from product_output folder to RadarImage model"

    def add_arguments(self, parser):
        parser.add_argument(
            '--product_root',
            type=str,
            default='/app/product_output',
            help='Root path to product_output folder (default: /app/product_output)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be done without creating records',
        )

    def handle(self, *args, **options):
        product_root = options['product_root']
        dry_run = options['dry_run']

        if not os.path.isdir(product_root):
            self.stderr.write(f"Product root not found: {product_root}")
            return

        self.stdout.write(f"Scanning {product_root}...")
        
        created = 0
        updated = 0
        skipped = 0
        errors = []

        # Pattern: RADAR_CODE_YYYYMMDDTHHmmssZ_PRODUCT_SWEEP.png
        # Example: RMA3_20251205T236000Z_DBZH_00.png
        pattern = re.compile(r'^([A-Z0-9]+)_(\d{8}T\d{6}Z)_([A-Z]+)(?:o)?_(\d{2})\.png$')

        with transaction.atomic():
            for root, dirs, files in os.walk(product_root):
                for filename in files:
                    if not filename.endswith('.png'):
                        continue

                    match = pattern.match(filename)
                    if not match:
                        self.stdout.write(
                            self.style.WARNING(f"Skipped (invalid name): {filename}")
                        )
                        skipped += 1
                        continue

                    radar_code, date_str, polarimetric_var, sweep_str = match.groups()

                    # Parse date from ISO format (e.g., 20251205T236000Z)
                    # Handle edge case: 23:60:00 -> 00:00:00 next day
                    try:
                        date_clean = date_str.rstrip('Z')
                        year = int(date_clean[0:4])
                        month = int(date_clean[4:6])
                        day = int(date_clean[6:8])
                        hour = int(date_clean[9:11])
                        minute = int(date_clean[11:13])
                        second = int(date_clean[13:15])
                        
                        # Handle overflow: 23:60:00 -> 00:00:00 next day
                        if hour == 23 and minute == 60:
                            dt = datetime(year, month, day, 0, 0, second)
                            dt = dt + timedelta(days=1)
                        else:
                            dt = datetime(year, month, day, hour, minute, second)
                        
                        # Make timezone aware (UTC) - use get_default_timezone() for UTC
                        from django.utils.timezone import make_aware
                        dt = make_aware(dt)  # uses DEFAULT_TIMEZONE from settings (UTC)
                    except (ValueError, IndexError) as e:
                        errors.append(f"{filename}: invalid date {date_str} ({e})")
                        skipped += 1
                        continue

                    # Get radar by code
                    try:
                        radar = Radar.objects.get(code=radar_code)
                    except Radar.DoesNotExist:
                        errors.append(f"{filename}: radar code {radar_code} not found in DB")
                        skipped += 1
                        continue

                    # Full path to the image
                    image_path = os.path.join(root, filename)
                    
                    # Relative path for media (product_output/RMA3/2025/12/05/filename.png)
                    relative_path = os.path.relpath(image_path, product_root)

                    # Default strategy and scanning from filename position
                    # If filename has extra fields, parse them; otherwise use defaults
                    strategy = 0
                    scanning = 0
                    sweep = float(sweep_str) if sweep_str else 0.0

                    # Create a unique key for the image (radar + date + polarimetric_var + sweep)
                    # to avoid duplicates and enable idempotent updates
                    try:
                        radar_image, created_flag = RadarImage.objects.update_or_create(
                            radar=radar,
                            date=dt,
                            polarimetric_var=polarimetric_var,
                            sweep=sweep,
                            defaults={
                                'image': relative_path,
                                'strategy': strategy,
                                'scanning': scanning,
                                'show_me': radar.is_active,  # show only if radar is active
                            }
                        )
                        if created_flag:
                            created += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"Created: {radar_code} {dt} {polarimetric_var}")
                            )
                        else:
                            updated += 1
                            self.stdout.write(
                                self.style.WARNING(f"Updated: {radar_code} {dt} {polarimetric_var}")
                            )
                    except Exception as e:
                        errors.append(f"{filename}: {e}")
                        skipped += 1
                        continue

        # Print summary
        self.stdout.write(self.style.SUCCESS("\n" + "="*60))
        self.stdout.write(self.style.SUCCESS(f"Sync completed:"))
        self.stdout.write(f"  Created: {created}")
        self.stdout.write(f"  Updated: {updated}")
        self.stdout.write(f"  Skipped: {skipped}")
        if errors:
            self.stdout.write(self.style.WARNING(f"\nErrors ({len(errors)}):"))
            for err in errors[:10]:  # show first 10 errors
                self.stdout.write(f"  - {err}")
            if len(errors) > 10:
                self.stdout.write(f"  ... and {len(errors) - 10} more")
