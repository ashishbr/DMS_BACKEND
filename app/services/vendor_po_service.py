"""
VendorPOService
---------------
Business logic for the standalone Vendor PO Generator.

Responsibilities:
  - Auto-generate PO numbers (VPO-YYYYMMDD-XXXX)
  - Compute subtotal / total_amount from line items when not supplied by caller
  - Persist GeneratedVendorPO + GeneratedVendorPOItem records
  - Mirror each GeneratedVendorPO as a VendorPO in the financial layer
    so it appears in clients-overview, margin reports, billing checks, etc.
  - Call pdf_generator.generate_vendor_po_pdf() and store the output path
  - Replace line items on update (delete-old / insert-new)
  - Regenerate PDF whenever PO data changes
  - Advance status via transition table and sync to the linked VendorPO

Status lifecycle:
  DRAFT → SENT → APPROVED → ACTIVE → CLOSED
  ACTIVE is set automatically when the first VendorInvoice is linked to the
  underlying VendorPO (handled by FinancialClassificationService / billing router).
"""
import os
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import GeneratedVendorPO, GeneratedVendorPOItem, VendorPO
from app.schemas import GeneratedVendorPOCreate, GeneratedVendorPOUpdate
from app.utils.pdf_generator import generate_vendor_po_pdf

# Directory where generated PDFs are stored (inside the main upload dir)
GENERATED_PO_DIR = os.path.join(settings.upload_dir, "generated_pos")

# Allowed forward-only status transitions
STATUS_TRANSITIONS = {
    "DRAFT":    {"SENT"},
    "SENT":     {"APPROVED", "DRAFT"},   # allow rolling back to DRAFT if sent in error
    "APPROVED": {"ACTIVE", "CLOSED"},
    "ACTIVE":   {"CLOSED"},
    "CLOSED":   set(),
}

# Map GeneratedVendorPO status → VendorPO status
# (VendorPO uses the financial layer's own lifecycle)
GENERATED_TO_VENDOR_STATUS = {
    "DRAFT":    "DRAFT",
    "SENT":     "DRAFT",      # vendor hasn't accepted yet
    "APPROVED": "APPROVED",
    "ACTIVE":   "ACTIVE",
    "CLOSED":   "CLOSED",
}


class VendorPOService:
    def __init__(self, db: Session):
        self.db = db

    # -----------------------------------------------------------------------
    # Public methods
    # -----------------------------------------------------------------------

    def create(self, payload: GeneratedVendorPOCreate) -> GeneratedVendorPO:
        """
        Create a GeneratedVendorPO, generate its PDF, and create a
        linked VendorPO in the financial layer so vendors appear in
        the clients-overview and margin reports immediately.
        """
        po_number = payload.po_number or self._generate_po_number()
        items = self._resolve_items(payload.line_items)
        subtotal = payload.subtotal if payload.subtotal is not None else sum(
            i["total_price"] for i in items
        )
        total_amount = payload.total_amount if payload.total_amount is not None else (
            subtotal + payload.tax - payload.discount
        )

        # 1. Create the financial-layer VendorPO (document_id=None for generated POs)
        vendor_po = VendorPO(
            id=str(uuid.uuid4()),
            document_id=None,
            vendor_po_number=po_number,
            vendor_name=payload.vendor_name,
            allocated_value=total_amount,
            currency="USD",
            service_description=payload.notes,
            issue_date=payload.issue_date or datetime.utcnow(),
            end_date=payload.delivery_date,
            status="DRAFT",
            is_generated=True,
        )
        self.db.add(vendor_po)
        self.db.flush()  # get vendor_po.id

        # 2. Create the GeneratedVendorPO linked to that VendorPO
        po = GeneratedVendorPO(
            id=str(uuid.uuid4()),
            po_number=po_number,
            vendor_name=payload.vendor_name,
            vendor_address=payload.vendor_address,
            vendor_email=payload.vendor_email,
            vendor_phone=payload.vendor_phone,
            client_name=payload.client_name,
            vendor_po_id=vendor_po.id,
            issue_date=payload.issue_date or datetime.utcnow(),
            delivery_date=payload.delivery_date,
            payment_terms=payload.payment_terms,
            subtotal=subtotal,
            tax=payload.tax,
            discount=payload.discount,
            total_amount=total_amount,
            notes=payload.notes,
            created_by=payload.created_by,
            status="DRAFT",
        )
        self.db.add(po)
        self.db.flush()  # get po.id before inserting items

        self._insert_items(po.id, items)
        self.db.flush()

        pdf_path = self._render_pdf(po, items)
        po.pdf_path = pdf_path

        self.db.commit()
        self.db.refresh(po)
        return po

    def get(self, po_id: str) -> Optional[GeneratedVendorPO]:
        return self.db.query(GeneratedVendorPO).filter(GeneratedVendorPO.id == po_id).first()

    def get_by_po_number(self, po_number: str) -> Optional[GeneratedVendorPO]:
        return (
            self.db.query(GeneratedVendorPO)
            .filter(GeneratedVendorPO.po_number == po_number)
            .first()
        )

    def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        client_name: Optional[str] = None,
    ) -> List[GeneratedVendorPO]:
        q = self.db.query(GeneratedVendorPO)
        if client_name:
            q = q.filter(GeneratedVendorPO.client_name == client_name)
        return q.order_by(GeneratedVendorPO.created_at.desc()).offset(skip).limit(limit).all()

    def advance_status(self, po_id: str, new_status: str) -> Optional[GeneratedVendorPO]:
        """
        Move a GeneratedVendorPO to new_status if the transition is allowed,
        then sync the linked VendorPO status.

        Returns the updated PO, or raises ValueError if the transition is invalid.
        """
        po = self.get(po_id)
        if not po:
            return None

        allowed = STATUS_TRANSITIONS.get(po.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from {po.status} to {new_status}. "
                f"Allowed: {allowed or 'none (terminal state)'}"
            )

        po.status = new_status

        # Sync to the linked VendorPO
        if po.vendor_po_id:
            vendor_po = self.db.query(VendorPO).filter(VendorPO.id == po.vendor_po_id).first()
            if vendor_po:
                vendor_po.status = GENERATED_TO_VENDOR_STATUS.get(new_status, new_status)

        self.db.commit()
        self.db.refresh(po)
        return po

    def update(self, po_id: str, payload: GeneratedVendorPOUpdate) -> Optional[GeneratedVendorPO]:
        """
        Partial update. If line_items are provided the old items are replaced.
        PDF is regenerated whenever any field changes.
        Financial fields on the linked VendorPO are kept in sync.
        """
        po = self.get(po_id)
        if not po:
            return None

        changed = False

        scalar_fields = [
            "vendor_name", "vendor_address", "vendor_email", "vendor_phone",
            "client_name", "delivery_date", "payment_terms", "notes",
        ]
        for field in scalar_fields:
            val = getattr(payload, field, None)
            if val is not None:
                setattr(po, field, val)
                changed = True

        # Status changes go through advance_status to enforce transitions
        if payload.status is not None and payload.status != po.status:
            try:
                return self.advance_status(po_id, payload.status)
            except ValueError:
                raise  # let the router return a 400

        for field in ("subtotal", "tax", "discount", "total_amount"):
            val = getattr(payload, field)
            if val is not None:
                setattr(po, field, val)
                changed = True

        items: Optional[List[dict]] = None
        if payload.line_items is not None:
            items = self._resolve_items(payload.line_items)
            self.db.query(GeneratedVendorPOItem).filter(
                GeneratedVendorPOItem.vendor_po_id == po_id
            ).delete()
            self._insert_items(po.id, items)

            if payload.subtotal is None:
                po.subtotal = sum(i["total_price"] for i in items)
            if payload.total_amount is None:
                po.total_amount = po.subtotal + po.tax - po.discount
            changed = True

        if changed:
            # Sync updated financials to the linked VendorPO
            if po.vendor_po_id:
                vendor_po = self.db.query(VendorPO).filter(VendorPO.id == po.vendor_po_id).first()
                if vendor_po:
                    vendor_po.allocated_value = po.total_amount
                    vendor_po.vendor_name = po.vendor_name
                    vendor_po.service_description = po.notes

            self.db.flush()
            current_items = items or self._load_items_as_dicts(po_id)
            po.pdf_path = self._render_pdf(po, current_items)
            self.db.commit()
            self.db.refresh(po)

        return po

    def delete(self, po_id: str) -> bool:
        po = self.get(po_id)
        if not po:
            return False

        vendor_po_id = po.vendor_po_id

        # Remove PDF file
        if po.pdf_path and os.path.exists(po.pdf_path):
            try:
                os.remove(po.pdf_path)
            except OSError:
                pass

        self.db.delete(po)
        self.db.flush()

        # Delete the linked VendorPO if it was auto-created (is_generated=True)
        if vendor_po_id:
            vendor_po = self.db.query(VendorPO).filter(
                VendorPO.id == vendor_po_id,
                VendorPO.is_generated == True,
            ).first()
            if vendor_po:
                self.db.delete(vendor_po)

        self.db.commit()
        return True

    def regenerate_pdf(self, po_id: str) -> Optional[str]:
        po = self.get(po_id)
        if not po:
            return None
        items = self._load_items_as_dicts(po_id)
        pdf_path = self._render_pdf(po, items)
        po.pdf_path = pdf_path
        self.db.commit()
        self.db.refresh(po)
        return pdf_path

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _generate_po_number(self) -> str:
        today_str = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"VPO-{today_str}-"
        # Find the highest sequence already used today, then go one higher.
        # Using MAX avoids collisions caused by deleted or failed records
        # that leave gaps in the count.
        from sqlalchemy import func as sa_func
        last = (
            self.db.query(sa_func.max(GeneratedVendorPO.po_number))
            .filter(GeneratedVendorPO.po_number.like(f"{prefix}%"))
            .scalar()
        )
        if last:
            try:
                last_seq = int(last.split("-")[-1])
            except (ValueError, IndexError):
                last_seq = 0
        else:
            last_seq = 0
        return f"{prefix}{last_seq + 1:04d}"

    @staticmethod
    def _resolve_items(raw_items) -> List[dict]:
        result = []
        for item in raw_items:
            total = item.total if item.total is not None else round(
                item.quantity * item.unit_price, 2
            )
            result.append({
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": total,
            })
        return result

    def _insert_items(self, po_id: str, items: List[dict]) -> None:
        for item in items:
            self.db.add(GeneratedVendorPOItem(
                id=str(uuid.uuid4()),
                vendor_po_id=po_id,
                description=item["description"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total_price=item["total_price"],
            ))

    def _load_items_as_dicts(self, po_id: str) -> List[dict]:
        rows = (
            self.db.query(GeneratedVendorPOItem)
            .filter(GeneratedVendorPOItem.vendor_po_id == po_id)
            .all()
        )
        return [
            {
                "description": r.description,
                "quantity": r.quantity,
                "unit_price": r.unit_price,
                "total_price": r.total_price,
            }
            for r in rows
        ]

    def _render_pdf(self, po: GeneratedVendorPO, items: List[dict]) -> str:
        os.makedirs(GENERATED_PO_DIR, exist_ok=True)
        output_path = os.path.join(GENERATED_PO_DIR, f"{po.po_number}.pdf")
        generate_vendor_po_pdf(
            output_path=output_path,
            po_number=po.po_number,
            vendor_name=po.vendor_name,
            vendor_address=po.vendor_address,
            vendor_email=po.vendor_email,
            vendor_phone=po.vendor_phone,
            issue_date=po.issue_date,
            delivery_date=po.delivery_date,
            payment_terms=po.payment_terms,
            line_items=items,
            subtotal=po.subtotal,
            tax=po.tax,
            discount=po.discount,
            total_amount=po.total_amount,
            notes=po.notes,
        )
        return output_path
