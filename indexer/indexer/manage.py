#!/usr/bin/env python
"""
Indexer management CLI.

Usage:
    python -m indexer.manage populate-cog-metadata     # Extract and update COG metadata
    python -m indexer.manage check                      # Check database connection
"""
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_check(args):
    """Check database connection."""
    from radar_db import check_db_connection
    from indexer.config import settings
    
    logger.info(f"Checking connection to: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    
    if check_db_connection():
        logger.info("✓ Database connection OK!")
        return 0
    else:
        logger.error("✗ Database connection FAILED!")
        return 1


def cmd_populate_cog_metadata(args):
    """
    Populate COG metadata (data_type, cmap, vmin, vmax) for all existing COG files.
    
    This command:
    1. Queries all RadarCOG records from the database
    2. Loads each COG file from disk
    3. Extracts metadata using extract_cog_metadata
    4. Updates the database records
    """
    from radar_db import db_manager, check_db_connection
    from radar_db.models import RadarCOG
    from indexer.config import settings
    from indexer.registrar import COGRegistrar
    
    if not check_db_connection():
        logger.error("Cannot connect to database.")
        return 1
    
    cog_base_path = Path(args.path or settings.watch_path)
    
    if not cog_base_path.exists():
        logger.error(f"COG base path does not exist: {cog_base_path}")
        return 1
    
    logger.info(f"Using COG base path: {cog_base_path}")
    
    with db_manager.get_session() as session:
        registrar = COGRegistrar(session, str(cog_base_path))
        
        # Query all COGs
        cogs = session.query(RadarCOG).all()
        total = len(cogs)
        
        if total == 0:
            logger.info("No COG files found in database")
            return 0
        
        logger.info(f"Found {total} COG files to process")
        
        updated_count = 0
        failed_count = 0
        skipped_count = 0
        
        for idx, cog in enumerate(cogs, 1):
            file_path = cog_base_path / cog.file_path
            
            if not file_path.exists():
                logger.warning(f"[{idx}/{total}] File not found: {cog.file_path}")
                failed_count += 1
                continue
            
            try:
                # Extract metadata
                metadata = registrar.extract_cog_metadata(file_path)
                
                if not metadata:
                    logger.warning(f"[{idx}/{total}] Failed to extract metadata: {cog.file_path}")
                    failed_count += 1
                    continue
                
                # Update only the new metadata fields
                if 'cog_data_type' in metadata:
                    cog.cog_data_type = metadata['cog_data_type']
                if 'cog_cmap' in metadata:
                    cog.cog_cmap = metadata['cog_cmap']
                if 'cog_vmin' in metadata:
                    cog.cog_vmin = metadata['cog_vmin']
                if 'cog_vmax' in metadata:
                    cog.cog_vmax = metadata['cog_vmax']
                
                session.commit()
                updated_count += 1
                logger.info(f"[{idx}/{total}] Updated: {cog.file_name} "
                          f"(type={metadata.get('cog_data_type')}, "
                          f"cmap={metadata.get('cog_cmap')})")
                
            except Exception as e:
                logger.error(f"[{idx}/{total}] Error processing {cog.file_path}: {e}")
                session.rollback()
                failed_count += 1
        
        # Summary
        print("\n" + "=" * 60)
        print(f"COG METADATA POPULATION SUMMARY")
        print("=" * 60)
        print(f"Total COGs:     {total}")
        print(f"Updated:        {updated_count}")
        print(f"Failed:         {failed_count}")
        print(f"Skipped:        {skipped_count}")
        print("=" * 60)
        
        return 0 if failed_count == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description='Indexer Management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m indexer.manage check                    # Test database connection
  python -m indexer.manage populate-cog-metadata    # Extract and update COG metadata
  python -m indexer.manage populate-cog-metadata -p /custom/path  # Custom path
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # check command
    check_parser = subparsers.add_parser('check', help='Check database connection')
    check_parser.set_defaults(func=cmd_check)
    
    # populate-cog-metadata command
    populate_parser = subparsers.add_parser('populate-cog-metadata', 
                                           help='Populate COG metadata for all indexed files')
    populate_parser.add_argument(
        '-p', '--path',
        help='Path to COG files (default: from settings.watch_path)'
    )
    populate_parser.set_defaults(func=cmd_populate_cog_metadata)
    
    # Parse arguments
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main() or 0)
