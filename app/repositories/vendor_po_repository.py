from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import VendorPO, VendorInvoice
from app.repositories.base_repository import BaseRepository


class VendorPORepository(BaseRepository[VendorPO]):
    def __init__(self, db: Session):
        super().__init__(VendorPO, db)

    def get_by_vendor_po_number(self, vendor_po_number: str) -> Optional[VendorPO]:
        return (
            self.db.query(VendorPO)
            .filter(VendorPO.vendor_po_number == vendor_po_number)
            .first()
        )

    def get_by_document_id(self, document_id: str) -> Optional[VendorPO]:
        return (
            self.db.query(VendorPO)
            .filter(VendorPO.document_id == document_id)
            .first()
        )

    def get_by_vendor_name(self, vendor_name: str) -> List[VendorPO]:
        return (
            self.db.query(VendorPO)
            .filter(VendorPO.vendor_name.ilike(f"%{vendor_name}%"))
            .all()
        )

    def get_by_client_po(self, client_po_id: str) -> List[VendorPO]:
        return (
            self.db.query(VendorPO)
            .filter(VendorPO.client_po_id == client_po_id)
            .all()
        )

    def get_total_invoiced(self, vendor_po_id: str) -> float:
        """Return SUM(invoice_amount) for non-duplicate invoices linked to this VendorPO."""
        result = (
            self.db.query(func.sum(VendorInvoice.invoice_amount))
            .filter(
                VendorInvoice.vendor_po_id == vendor_po_id,
                VendorInvoice.is_duplicate == False,
            )
            .scalar()
        )
        return float(result or 0.0)

    def find_by_vendor_name_fuzzy(self, vendor_name: str, limit: int = 5) -> List[VendorPO]:
        """Simple ILIKE-based fuzzy search on vendor name."""
        # Extract first meaningful token to broaden the match
        token = vendor_name.split()[0] if vendor_name else vendor_name
        return (
            self.db.query(VendorPO)
            .filter(VendorPO.vendor_name.ilike(f"%{token}%"))
            .limit(limit)
            .all()
        )

    def get_unlinked(self) -> List[VendorPO]:
        """Vendor POs not yet linked to any Client PO."""
        return (
            self.db.query(VendorPO)
            .filter(VendorPO.client_po_id.is_(None))
            .all()
        )
