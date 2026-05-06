# indexer/indexer/main.py
#!/usr/bin/env python
"""
Main entry point for the COG indexer service.
"""
import logging
import os
import sys
import threading
import time
import argparse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def wait_for_database(max_retries: int = 30, delay: int = 2) -> bool:
    """Wait for database to be available."""
    from radar_db import check_db_connection
    
    for i in range(max_retries):
        if check_db_connection():
            logger.info("Database connection established")
            return True
        logger.warning(f"Database not ready, retrying in {delay}s... ({i+1}/{max_retries})")
        time.sleep(delay)
    
    logger.error("Could not connect to database")
    return False


def run_indexer():
    """Run the indexer service."""
    from radar_db import db_manager
    from indexer.watcher import COGWatcher, TopsAndCoresWatcher

    # Wait for database
    if not wait_for_database():
        sys.exit(1)

    # Resolve the TopsAndCores directory from environment
    tops_and_cores_dir = os.getenv("TOPS_AND_CORES_DIR", "/tops_and_cores")
    if not os.getenv("TOPS_AND_CORES_DIR"):
        logger.warning(
            "TOPS_AND_CORES_DIR environment variable is not set. "
            f"Using default: {tops_and_cores_dir}"
        )

    # Start TopsAndCoresWatcher in a background thread
    tc_watcher = TopsAndCoresWatcher(tops_and_cores_dir)
    tc_thread = threading.Thread(
        target=tc_watcher.run_forever,
        args=(db_manager.get_session_direct,),
        name="tops-and-cores-watcher",
        daemon=True,
    )
    tc_thread.start()
    logger.info(f"TopsAndCores watcher started (dir={tops_and_cores_dir})")

    # Run COGWatcher on the main thread (blocks forever)
    watcher = COGWatcher()
    watcher.run_forever(db_manager.get_session_direct)


def run_single_scan():
    """Run a single scan (useful for testing or cron)."""
    from radar_db import db_manager
    from indexer.watcher import COGWatcher
    
    if not wait_for_database(max_retries=5):
        sys.exit(1)
    
    watcher = COGWatcher()
    session = db_manager.get_session_direct()
    try:
        count = watcher.run_scan(session)
        session.commit()
        logger.info(f"Single scan complete: indexed {count} files")
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description='COG Indexer Service')
    parser.add_argument('--single', action='store_true', 
                       help='Run a single scan and exit')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.single:
        run_single_scan()
    else:
        run_indexer()


if __name__ == '__main__':
    main()