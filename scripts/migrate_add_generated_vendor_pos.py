"""
Migration: create generated_vendor_pos and generated_vendor_po_items tables
(and add client_name column if table exists without it).
Run once: python scripts/migrate_add_generated_vendor_pos.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine, Base
from app.models import GeneratedVendorPO, GeneratedVendorPOItem  # noqa: F401 — registers models


def migrate():
    print("Starting migration: generated_vendor_pos …")

    with engine.connect() as conn:
        # Check whether the table exists at all
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'generated_vendor_pos'
            )
        """))
        table_exists = result.scalar()

        if not table_exists:
            print("  Table does not exist — creating via Base.metadata.create_all …")
            # Create only the two new tables, leave everything else untouched
            Base.metadata.create_all(
                bind=engine,
                tables=[
                    GeneratedVendorPO.__table__,
                    GeneratedVendorPOItem.__table__,
                ],
                checkfirst=True,
            )
            print("  ✓ Tables created.")
        else:
            print("  Table already exists — checking columns …")

            # Check for client_name column
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'generated_vendor_pos'
                      AND column_name = 'client_name'
                )
            """))
            has_client_name = result.scalar()

            if not has_client_name:
                print("  ➕ Adding client_name column …")
                conn.execute(text(
                    "ALTER TABLE generated_vendor_pos ADD COLUMN client_name VARCHAR"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_generated_vendor_pos_client_name "
                    "ON generated_vendor_pos (client_name)"
                ))
                conn.commit()
                print("  ✓ client_name column added.")
            else:
                print("  ✓ client_name column already exists.")

            # Check for generated_vendor_po_items table
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'generated_vendor_po_items'
                )
            """))
            items_exists = result.scalar()

            if not items_exists:
                print("  ➕ Creating generated_vendor_po_items table …")
                Base.metadata.create_all(
                    bind=engine,
                    tables=[GeneratedVendorPOItem.__table__],
                    checkfirst=True,
                )
                print("  ✓ generated_vendor_po_items table created.")
            else:
                print("  ✓ generated_vendor_po_items table already exists.")

    print("Migration complete.")


if __name__ == "__main__":
    migrate()
