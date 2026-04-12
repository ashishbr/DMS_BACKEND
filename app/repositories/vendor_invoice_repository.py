from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models import VendorInvoice
from app.repositories.base_repository import BaseRepository


class VendorInvoiceRepository(BaseRepository[VendorInvoice]):
    def __init__(self, db: Session):
        super().__init__(VendorInvoice, db)

    def get_by_document_id(self, document_id: str) -> Optional[VendorInvoice]:
        return (
            self.db.query(VendorInvoice)
            .filter(VendorInvoice.document_id == document_id)
            .first()
        )

    def get_by_vendor_po(self, vendor_po_id: str) -> List[VendorInvoice]:
        return (
            self.db.query(VendorInvoice)
            .filter(VendorInvoice.vendor_po_id == vendor_po_id)
            .all()
        )

    def get_unlinked(self) -> List[VendorInvoice]:
        return (
            self.db.query(VendorInvoice)
            .filter(VendorInvoice.vendor_po_id.is_(None))
            .all()
        )

    def get_overbilling_flags(self) -> List[VendorInvoice]:
        return (
            self.db.query(VendorInvoice)
            .filter(VendorInvoice.overbilling_flag == True)
            .all()
        )

    def get_sum_by_vendor_po(self, vendor_po_id: str) -> float:
        """Sum of non-duplicate invoice amounts for a VendorPO."""
        result = (
            self.db.query(func.sum(VendorInvoice.invoice_amount))
            .filter(
                VendorInvoice.vendor_po_id == vendor_po_id,
                VendorInvoice.is_duplicate == False,
            )
            .scalar()
        )
        return float(result or 0.0)

    def find_hard_duplicate(self, invoice_number: str, vendor_name: str) -> Optional[VendorInvoice]:
        """Exact invoice_number + vendor_name match."""
        return (
            self.db.query(VendorInvoice)
            .filter(
                VendorInvoice.invoice_number == invoice_number,
                VendorInvoice.vendor_name == vendor_name,
            )
            .first()
        )

    def find_soft_duplicates(
        self,
        vendor_name: str,
        invoice_amount: float,
        invoice_date: Optional[datetime],
        exclude_id: Optional[str] = None,
        window_days: int = 7,
        amount_tolerance: float = 0.01,
    ) -> List[VendorInvoice]:
        """
        Same vendor + amount within tolerance + date within window_days.
        Used for soft-duplicate detection.
        """
        amount_min = invoice_amount * (1 - amount_tolerance)
        amount_max = invoice_amount * (1 + amount_tolerance)

        query = self.db.query(VendorInvoice).filter(
            VendorInvoice.vendor_name == vendor_name,
            VendorInvoice.invoice_amount >= amount_min,
            VendorInvoice.invoice_amount <= amount_max,
        )

        if invoice_date:
            date_min = invoice_date - timedelta(days=window_days)
            date_max = invoice_date + timedelta(days=window_days)
            query = query.filter(
                VendorInvoice.invoice_date >= date_min,
                VendorInvoice.invoice_date <= date_max,
            )

        if exclude_id:
            query = query.filter(VendorInvoice.id != exclude_id)

        return query.all()

    def get_all_overbilled_by_vendor_po(self) -> List[VendorInvoice]:
        return (
            self.db.query(VendorInvoice)
            .filter(VendorInvoice.status == "OVERBILLING_DETECTED")
            .all()
        )
