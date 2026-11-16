import unittest
from sqlalchemy import create_engine, inspect
from app.db.base import Base
from app.db.migrations import migrate_hardware_specifications
from app.db.models import Hardware, HardwareSpecification


class HardwareSpecMigrationTests(unittest.TestCase):
    def test_additive_migration_preserves_legacy_hardware_and_is_idempotent(self):
        engine = create_engine('sqlite:///:memory:')
        try:
            Hardware.__table__.create(engine)
            from sqlalchemy.orm import Session
            with Session(engine) as db:
                db.add(Hardware(type='CPU', name='legacy CPU', raw_score=1, normalized_score=1))
                db.commit()
            migrate_hardware_specifications(engine)
            migrate_hardware_specifications(engine)
            with Session(engine) as db:
                self.assertEqual(db.query(Hardware).count(), 1)
                self.assertEqual(db.query(HardwareSpecification).count(), 0)
            self.assertIn('hardware_specifications', inspect(engine).get_table_names())
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
