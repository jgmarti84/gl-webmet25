# shared/radar_db/manage.py
#!/usr/bin/env python
"""
Database management CLI for the Radar COG system.

Usage:
    python -m radar_db.manage init          # Initialize database tables
    python -m radar_db.manage seed          # Load seed data
    python -m radar_db.manage check         # Check database connection
    python -m radar_db.manage reset         # Reset database (DESTRUCTIVE)
    python -m radar_db.manage info          # Show database info
    python -m radar_db.manage migrate       # Run Alembic migrations
"""
import argparse
import logging
import sys
import os
from radar_db.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_init(args):
    """Initialize the database (create tables)."""
    from .database import init_db, check_db_connection
    # from .config import settings
    
    logger.info(f"Connecting to database: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    
    if not check_db_connection():
        logger.error("Cannot connect to database. Please check your settings.")
        return 1
    
    logger.info("Creating database tables...")
    init_db()
    logger.info("Database initialized successfully!")
    return 0


def cmd_seed(args):
    """Load seed data into the database."""
    from radar_db.seeds import run_seeds
    from radar_db.database import check_db_connection
    
    if not check_db_connection():
        logger.error("Cannot connect to database. Please check your settings.")
        return 1
    
    logger.info(f"Loading seed data from: {args.file}")
    results = run_seeds(args.file if args.file != 'default' else None)
    
    if 'error' in results:
        logger.error(f"Seeding failed: {results['error']}")
        return 1
    
    logger.info("Seed data loaded successfully!")
    for model, count in results.items():
        logger.info(f"  {model}: {count} records")
    return 0


def cmd_check(args):
    """Check database connection."""
    from radar_db.database import check_db_connection
    from radar_db.config import settings
    
    logger.info(f"Checking connection to: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    
    if check_db_connection():
        logger.info("✓ Database connection OK!")
        return 0
    else:
        logger.error("✗ Database connection FAILED!")
        return 1


def cmd_reset(args):
    """Reset database (drop all tables and recreate)."""
    from radar_db.database import db_manager, check_db_connection
    from radar_db.seeds import run_seeds
    
    if not check_db_connection():
        logger.error("Cannot connect to database.")
        return 1
    
    if not args.force:
        confirm = input("⚠️  This will DELETE ALL DATA. Are you sure? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("Aborted.")
            return 0
    
    logger.warning("Dropping all tables...")
    db_manager.drop_all_tables()
    
    logger.info("Recreating tables...")
    db_manager.create_all_tables()
    
    logger.info("Database reset complete!")
    
    if args.seed:
        logger.info("Loading seed data...")
        results = run_seeds()
        logger.info(f"Seed data loaded: {results}")
    
    return 0


def cmd_info(args):
    """Show database information and statistics."""
    from radar_db.database import db_manager, check_db_connection
    from radar_db.models import Radar, RadarProduct, Reference, RadarCOG, Volumen, Estrategia
    from radar_db.config import settings
    
    if not check_db_connection():
        logger.error("Cannot connect to database.")
        return 1
    
    print("\n" + "=" * 50)
    print("DATABASE INFORMATION")
    print("=" * 50)
    print(f"Host:     {settings.db_host}")
    print(f"Port:     {settings.db_port}")
    print(f"Database: {settings.db_name}")
    print(f"User:     {settings.db_user}")
    print("=" * 50)
    
    with db_manager.get_session() as session:
        print("\nTABLE COUNTS:")
        print("-" * 30)
        
        tables = [
            ("Radars", Radar),
            ("Products", RadarProduct),
            ("References", Reference),
            ("Volumenes", Volumen),
            ("Estrategias", Estrategia),
            ("COG Files", RadarCOG),
        ]
        
        for name, model in tables:
            try:
                count = session.query(model).count()
                print(f"  {name:20s}: {count:>6}")
            except Exception as e:
                print(f"  {name:20s}: ERROR - {e}")
        
        print("-" * 30)
        
        # Show radar details
        radars = session.query(Radar).filter_by(is_active=True).all()
        if radars:
            print("\nACTIVE RADARS:")
            for radar in radars:
                cog_count = session.query(RadarCOG).filter_by(radar_code=radar.code).count()
                print(f"  {radar.code:8s} - {radar.title:20s} ({cog_count} COGs)")
        
        # Show recent COGs
        recent_cogs = session.query(RadarCOG).order_by(
            RadarCOG.created_at.desc()
        ).limit(5).all()
        
        if recent_cogs:
            print("\nRECENT COG FILES:")
            for cog in recent_cogs:
                print(f"  [{cog.radar_code}] {cog.file_name} - {cog.observation_time}")
    
    print("\n")
    return 0


def cmd_migrate(args):
    """Run Alembic migrations."""
    import subprocess
    
    # Ensure we're in the right directory for alembic
    alembic_paths = [
        "alembic.ini",
        "/app/alembic.ini",
        os.path.join(os.path.dirname(__file__), "..", "alembic.ini"),
    ]
    
    alembic_ini = None
    for path in alembic_paths:
        if os.path.exists(path):
            alembic_ini = path
            break
    
    if alembic_ini is None:
        logger.error("Could not find alembic.ini")
        return 1
    
    alembic_cmd = ['alembic', '-c', alembic_ini]
    
    if args.action == 'upgrade':
        target = args.revision or 'head'
        cmd = alembic_cmd + ['upgrade', target]
        logger.info(f"Upgrading to: {target}")
        
    elif args.action == 'downgrade':
        target = args.revision or '-1'
        cmd = alembic_cmd + ['downgrade', target]
        logger.info(f"Downgrading to: {target}")
        
    elif args.action == 'generate':
        if not args.message:
            logger.error("Please provide a migration message with -m")
            return 1
        cmd = alembic_cmd + ['revision', '--autogenerate', '-m', args.message]
        logger.info(f"Generating migration: {args.message}")
        
    elif args.action == 'history':
        cmd = alembic_cmd + ['history', '--verbose']
        
    elif args.action == 'current':
        cmd = alembic_cmd + ['current']
        
    else:
        logger.error(f"Unknown migration action: {args.action}")
        return 1
    
    result = subprocess.run(cmd)
    return result.returncode


def cmd_shell(args):
    """Open an interactive Python shell with database access."""
    try:
        from IPython import embed
        use_ipython = True
    except ImportError:
        use_ipython = False
    
    from radar_db.database import db_manager, get_db
    from radar_db.models import Radar, RadarProduct, Reference, RadarCOG, Volumen, Estrategia
    from radar_db.config import settings
    
    # Create a session for interactive use
    session = db_manager.get_session_direct()
    
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                   Radar DB Interactive Shell                  ║
╠══════════════════════════════════════════════════════════════╣
║  Available objects:                                           ║
║    session    - SQLAlchemy session                           ║
║    Radar, RadarProduct, Reference, RadarCOG, etc. - Models   ║
║    settings   - Configuration                                 ║
║                                                               ║
║  Example:                                                     ║
║    radars = session.query(Radar).all()                       ║
║    session.query(RadarCOG).count()                           ║
╚══════════════════════════════════════════════════════════════╝
"""
    
    print(banner)
    
    # Make variables available in shell
    namespace = {
        'session': session,
        'db_manager': db_manager,
        'settings': settings,
        'Radar': Radar,
        'RadarProduct': RadarProduct,
        'Reference': Reference,
        'RadarCOG': RadarCOG,
        'Volumen': Volumen,
        'Estrategia': Estrategia,
    }
    
    if use_ipython:
        embed(user_ns=namespace)
    else:
        import code
        code.interact(local=namespace)
    
    session.close()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Radar COG Database Management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m radar_db.manage init                    # Create tables
  python -m radar_db.manage seed                    # Load seed data
  python -m radar_db.manage seed -f custom.json     # Load custom seed file
  python -m radar_db.manage check                   # Test connection
  python -m radar_db.manage info                    # Show database stats
  python -m radar_db.manage reset --seed            # Reset and reseed
  python -m radar_db.manage migrate upgrade         # Run migrations
  python -m radar_db.manage migrate generate -m "add field"
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # init command
    init_parser = subparsers.add_parser('init', help='Initialize database tables')
    init_parser.set_defaults(func=cmd_init)
    
    # seed command
    seed_parser = subparsers.add_parser('seed', help='Load seed data')
    seed_parser.add_argument(
        '-f', '--file', 
        default='default',
        help='Path to seed data JSON file (default: auto-detect)'
    )
    seed_parser.set_defaults(func=cmd_seed)
    
    # check command
    check_parser = subparsers.add_parser('check', help='Check database connection')
    check_parser.set_defaults(func=cmd_check)
    
    # info command
    info_parser = subparsers.add_parser('info', help='Show database information')
    info_parser.set_defaults(func=cmd_info)
    
    # reset command
    reset_parser = subparsers.add_parser('reset', help='Reset database (DESTRUCTIVE)')
    reset_parser.add_argument(
        '--force', 
        action='store_true', 
        help='Skip confirmation prompt'
    )
    reset_parser.add_argument(
        '--seed', 
        action='store_true', 
        help='Load seed data after reset'
    )
    reset_parser.set_defaults(func=cmd_reset)
    
    # migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Run Alembic migrations')
    migrate_parser.add_argument(
        'action', 
        choices=['upgrade', 'downgrade', 'generate', 'history', 'current'],
        help='Migration action to perform'
    )
    migrate_parser.add_argument(
        '-m', '--message', 
        help='Migration message (for generate)'
    )
    migrate_parser.add_argument(
        '-r', '--revision',
        help='Target revision (for upgrade/downgrade)'
    )
    migrate_parser.set_defaults(func=cmd_migrate)
    
    # shell command
    shell_parser = subparsers.add_parser('shell', help='Open interactive shell')
    shell_parser.set_defaults(func=cmd_shell)
    
    # Parse arguments
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main() or 0)