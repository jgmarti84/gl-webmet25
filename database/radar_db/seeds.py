# shared/radar_db/seeds.py
"""
Seed data loader for initial database population.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from decimal import Decimal

from sqlalchemy.orm import Session

from radar_db.database import db_manager
from radar_db.models import Radar, RadarProduct, Reference, Volumen, Estrategia

logger = logging.getLogger(__name__)


class DataSeeder:
    """Handles loading initial/seed data into the database."""
    
    def __init__(self, data_file: Optional[str] = None):
        # Default path - can be overridden
        if data_file is None:
            # Try multiple possible locations
            possible_paths = [
                Path("seed_data/initial_data.json"),
                Path("/app/seed_data/initial_data.json"),
                Path(__file__).parent.parent / "seed_data" / "initial_data.json",
            ]
            for path in possible_paths:
                if path.exists():
                    self.data_file = path
                    break
            else:
                self.data_file = Path("seed_data/initial_data.json")
        else:
            self.data_file = Path(data_file)
        
        self.data: List[Dict[str, Any]] = []
    
    def load_json(self) -> bool:
        """Load data from JSON file."""
        if not self.data_file.exists():
            logger.error(f"Seed data file not found: {self.data_file}")
            logger.info(f"Current working directory: {Path.cwd()}")
            return False
        
        with open(self.data_file, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        logger.info(f"Loaded {len(self.data)} records from {self.data_file}")
        return True
    
    def _group_by_model(self) -> Dict[str, List[Dict]]:
        """Group records by model type."""
        groups: Dict[str, List[Dict]] = {}
        for record in self.data:
            # Handle both "radar_api.radar" and "radar" formats
            model_name = record.get('model', '').split('.')[-1].lower()
            if model_name not in groups:
                groups[model_name] = []
            groups[model_name].append(record)
        return groups
    
    def seed_radars(self, session: Session, records: List[Dict]) -> int:
        """Seed radar stations."""
        count = 0
        for record in records:
            pk = record.get('pk')
            fields = record.get('fields', {})
            
            # Check if exists
            existing = session.query(Radar).filter_by(code=pk).first()
            if existing:
                # Update existing radar if point values are missing or null
                if (existing.point1_lat is None or existing.point1_long is None or 
                    existing.point2_lat is None or existing.point2_long is None):
                    logger.debug(f"Updating missing point values for radar {pk}")
                    existing.point1_lat = Decimal(str(fields.get('point1_lat', 0)))
                    existing.point1_long = Decimal(str(fields.get('point1_long', 0)))
                    existing.point2_lat = Decimal(str(fields.get('point2_lat', 0)))
                    existing.point2_long = Decimal(str(fields.get('point2_long', 0)))
                    count += 1
                else:
                    logger.debug(f"Radar {pk} already exists with all values, skipping")
                continue
            
            radar = Radar(
                code=pk,
                title=fields.get('title', ''),
                description=fields.get('description', ''),
                center_lat=Decimal(str(fields.get('center_lat', 0))),
                center_long=Decimal(str(fields.get('center_long', 0))),
                img_radio=fields.get('img_radio', 240),
                is_active=fields.get('is_active', True),
                point1_lat=Decimal(str(fields.get('point1_lat', 0))),
                point1_long=Decimal(str(fields.get('point1_long', 0))),
                point2_lat=Decimal(str(fields.get('point2_lat', 0))),
                point2_long=Decimal(str(fields.get('point2_long', 0))),
            )
            session.add(radar)
            count += 1
            logger.debug(f"Added radar: {pk}")
        
        return count
    
    def seed_products(self, session: Session, records: List[Dict]) -> int:
        """Seed radar products."""
        count = 0
        for record in records:
            pk = record.get('pk')
            fields = record.get('fields', {})
            
            product_key = fields.get('product_key', '')
            
            # Check if exists by product_key (more reliable than pk)
            existing = session.query(RadarProduct).filter_by(product_key=product_key).first()
            if existing:
                logger.debug(f"Product {product_key} already exists, skipping")
                continue
            
            product = RadarProduct(
                id=pk,  # Preserve original ID for reference relationships
                product_key=product_key,
                product_title=fields.get('product_title', ''),
                product_description=fields.get('product_description', ''),
                enabled=fields.get('enabled', True),
                see_in_open=fields.get('see_in_open', False),
            )
            session.add(product)
            count += 1
            logger.debug(f"Added product: {product_key}")
        
        return count
    
    def seed_references(self, session: Session, records: List[Dict]) -> int:
        """Seed color references."""
        count = 0
        for record in records:
            pk = record.get('pk')
            fields = record.get('fields', {})
            
            # Check if product exists
            product_id = fields.get('product')
            product = session.query(RadarProduct).filter_by(id=product_id).first()
            if not product:
                logger.warning(f"Product {product_id} not found for reference {pk}, skipping")
                continue
            
            # Check if reference already exists
            existing = session.query(Reference).filter_by(id=pk).first()
            if existing:
                logger.debug(f"Reference {pk} already exists, skipping")
                continue
            
            reference = Reference(
                id=pk,
                product_id=product_id,
                title=fields.get('title', ''),
                description=fields.get('description', ''),
                unit=fields.get('unit', ''),
                value=float(fields.get('value', 0)),
                color=fields.get('color', '#000000'),
                color_font=fields.get('color_font', '#FFFFFF'),
            )
            session.add(reference)
            count += 1
        
        logger.debug(f"Added {count} references")
        return count
    
    def seed_volumenes(self, session: Session, records: List[Dict]) -> int:
        """Seed volumenes."""
        count = 0
        for record in records:
            pk = record.get('pk')
            fields = record.get('fields', {})
            
            existing = session.query(Volumen).filter_by(id=pk).first()
            if existing:
                logger.debug(f"Volumen {pk} already exists, skipping")
                continue
            
            volumen = Volumen(
                id=pk,
                value=fields.get('value', 0),
            )
            session.add(volumen)
            count += 1
        
        logger.debug(f"Added {count} volumenes")
        return count
    
    def seed_estrategias(self, session: Session, records: List[Dict]) -> int:
        """Seed estrategias with their volumen relationships."""
        count = 0
        for record in records:
            pk = record.get('pk')
            fields = record.get('fields', {})
            
            existing = session.query(Estrategia).filter_by(code=pk).first()
            if existing:
                logger.debug(f"Estrategia {pk} already exists, skipping")
                continue
            
            estrategia = Estrategia(
                code=pk,
                description=fields.get('description', ''),
            )
            
            # Add volumen relationships
            volumen_ids = fields.get('volumenes', [])
            for vol_id in volumen_ids:
                volumen = session.query(Volumen).filter_by(id=vol_id).first()
                if volumen:
                    estrategia.volumenes.append(volumen)
                else:
                    logger.warning(f"Volumen {vol_id} not found for estrategia {pk}")
            
            session.add(estrategia)
            count += 1
        
        logger.debug(f"Added {count} estrategias")
        return count
    
    def seed_all(self) -> Dict[str, int]:
        """
        Seed all data in the correct order (respecting foreign keys).
        
        Returns:
            Dictionary with counts of records added per model
        """
        if not self.load_json():
            return {"error": "Could not load seed data file"}
        
        groups = self._group_by_model()
        results = {}
        
        logger.info(f"Found model groups: {list(groups.keys())}")
        
        with db_manager.get_session() as session:
            # Order matters due to foreign key constraints!
            
            # 1. Radars (no dependencies)
            if 'radar' in groups:
                results['radars'] = self.seed_radars(session, groups['radar'])
                session.flush()
            
            # 2. Products (no dependencies)
            if 'radarproduct' in groups:
                results['products'] = self.seed_products(session, groups['radarproduct'])
                session.flush()
            
            # 3. References (depends on products)
            if 'reference' in groups:
                results['references'] = self.seed_references(session, groups['reference'])
                session.flush()
            
            # 4. Volumenes (no dependencies)
            if 'volumen' in groups:
                results['volumenes'] = self.seed_volumenes(session, groups['volumen'])
                session.flush()
            
            # 5. Estrategias (depends on volumenes)
            if 'estrategia' in groups:
                results['estrategias'] = self.seed_estrategias(session, groups['estrategia'])
        
        logger.info(f"Seeding complete: {results}")
        return results


def run_seeds(data_file: Optional[str] = None) -> Dict[str, int]:
    """
    Convenience function to run the seeding process.
    
    Args:
        data_file: Optional path to seed data JSON file
        
    Returns:
        Dictionary with counts of records added
    """
    seeder = DataSeeder(data_file)
    return seeder.seed_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = run_seeds()
    print(f"Seeding results: {results}")