"""
Billing Validation Service
---------------------------
Enforces the core financial constraint of Layer 3:

  SUM(VendorInvoice.invoice_amount per VendorPO) ≤ VendorPO.allocated_value

Also reports over-allocation warnings at the Client PO level (Layer 2):

  SUM(POAllocation.allocated_value per ClientPO) vs ClientPO.total_value

When overbilling is detected:
  - Sets VendorInvoice.overbilling_flag = True
  - Sets VendorInvoice.overbilling_amount = excess
  - Sets VendorInvoice.status = OVERBILLING_DETECTED
  - Creates a critical Alert in the alerts table
"""
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import VendorInvoice, VendorPO, Alert
from app.repositories.vendor_po_repository import VendorPORepository
from app.repositories.vendor_invoice_repository import VendorInvoiceRepository
from app.repositories.po_mapping_repository import POMappingRepository
from app.repositories.client_po_repository import ClientPORepository
from app.schemas import BillingViolation, BillingViolationsResponse, VendorPOConsumption


class BillingValidationService:
    def __init__(self, db: Session):
        self.db = db
        self.vendor_po_repo = VendorPORepository(db)
        self.vendor_inv_repo = VendorInvoiceRepository(db)
        self.mapping_repo = POMappingRepository(db)
        self.client_po_repo = ClientPORepository(db)

    # ------------------------------------------------------------------
    # Vendor PO overbilling check
    # ------------------------------------------------------------------

    def check_vendor_po_overbilling(self, vendor_po_id: str) -> VendorPOConsumption:
        """
        Calculate total invoiced vs allocated_value for a VendorPO.
        If overbilled, flags all non-duplicate invoices whose cumulative sum
        pushed the PO over the cap.
        Returns a consumption summary.
        """
        vendor_po = self.vendor_po_repo.get(vendor_po_id)
        if not vendor_po:
            raise ValueError(f"VendorPO {vendor_po_id} not found")

        invoices = self.vendor_inv_repo.get_by_vendor_po(vendor_po_id)
        valid_invoices = [inv for inv in invoices if not inv.is_duplicate]
        total_invoiced = sum(inv.invoice_amount for inv in valid_invoices)

        cap = vendor_po.allocated_value
        remaining = cap - total_invoiced
        utilization_pct = (total_invoiced / cap * 100) if cap > 0 else 0.0
        is_overbilled = total_invoiced > cap
        overbilled_by = (total_invoiced - cap) if is_overbilled else None

        if is_overbilled:
            self._flag_overbilling(valid_invoices, cap, vendor_po)

        return VendorPOConsumption(
            vendor_po_id=vendor_po.id,
            vendor_po_number=vendor_po.vendor_po_number,
            vendor_name=vendor_po.vendor_name,
            allocated_value=cap,
            total_invoiced=total_invoiced,
            remaining=remaining,
            utilization_pct=round(utilization_pct, 2),
            is_overbilled=is_overbilled,
            overbilled_by=overbilled_by,
            invoice_count=len(valid_invoices),
            currency=vendor_po.currency,
        )

    def _flag_overbilling(
        self,
        invoices: List[VendorInvoice],
        cap: float,
        vendor_po: VendorPO,
    ) -> None:
        """
        Walk invoices in creation order, find the crossing point, and flag
        all invoices beyond the cap as OVERBILLING_DETECTED.
        Also creates a critical Alert.
        """
        running = 0.0
        crossed = False

        for inv in sorted(invoices, key=lambda x: x.created_at):
            running += inv.invoice_amount
            if running > cap:
                excess = running - cap
                inv.overbilling_flag = True
                inv.overbilling_amount = round(excess, 4)
                inv.status = "OVERBILLING_DETECTED"
                crossed = True

        if crossed:
            self.db.flush()
            total_invoiced = sum(inv.invoice_amount for inv in invoices)
            self._create_overbilling_alert(vendor_po, total_invoiced, cap)

    def _create_overbilling_alert(
        self,
        vendor_po: VendorPO,
        total_invoiced: float,
        cap: float,
    ) -> None:
        """Create a critical Alert for overbilling. Idempotent — skips if one exists."""
        existing = (
            self.db.query(Alert)
            .filter(
                Alert.document_id == vendor_po.document_id,
                Alert.level == "critical",
                Alert.title.like("Vendor PO Overbilling%"),
                Alert.acknowledged == False,
            )
            .first()
        )
        if existing:
            return

        alert = Alert(
            id=str(uuid.uuid4()),
            title=f"Vendor PO Overbilling: {vendor_po.vendor_po_number}",
            description=(
                f"Vendor PO {vendor_po.vendor_po_number} ({vendor_po.vendor_name}) "
                f"has been overbilled. Total invoiced: {total_invoiced:,.2f} "
                f"{vendor_po.currency} against a cap of {cap:,.2f} {vendor_po.currency}. "
                f"Excess: {total_invoiced - cap:,.2f} {vendor_po.currency}."
            ),
            level="critical",
            document_id=vendor_po.document_id,
            timestamp=datetime.utcnow(),
            acknowledged=False,
        )
        self.db.add(alert)
        self.db.flush()

    # ------------------------------------------------------------------
    # Client PO over-allocation check (warning only)
    # ------------------------------------------------------------------

    def check_client_po_allocation_cap(self, client_po_id: str) -> Dict[str, Any]:
        """
        Check if allocations exceed the Client PO total_value.
        This is a WARNING — not a block. Returns the warning payload.
        """
        client_po = self.client_po_repo.get(client_po_id)
        if not client_po:
            raise ValueError(f"ClientPO {client_po_id} not found")

        total_allocated = self.mapping_repo.get_total_allocated(client_po_id)
        over = total_allocated > client_po.total_value
        excess = (total_allocated - client_po.total_value) if over else 0.0

        return {
            "client_po_id": client_po_id,
            "po_number": client_po.po_number,
            "total_value": client_po.total_value,
            "total_allocated": total_allocated,
            "over_allocated": over,
            "excess": excess,
            "currency": client_po.currency,
        }

    # ------------------------------------------------------------------
    # Global violations report
    # ------------------------------------------------------------------

    def get_all_violations(self) -> BillingViolationsResponse:
        """
        Scan all VendorPOs and ClientPOs and return a consolidated violations report.
        """
        vendor_po_violations: List[BillingViolation] = []
        client_po_violations: List[BillingViolation] = []

        # Vendor PO violations
        all_vendor_pos = self.vendor_po_repo.get_all(limit=10000)
        for vpo in all_vendor_pos:
            total_invoiced = self.vendor_inv_repo.get_sum_by_vendor_po(vpo.id)
            if total_invoiced > vpo.allocated_value:
                excess = total_invoiced - vpo.allocated_value
                vendor_po_violations.append(
                    BillingViolation(
                        violation_type="VENDOR_PO_OVERBILLED",
                        entity_id=vpo.id,
                        entity_ref=vpo.vendor_po_number,
                        cap_value=vpo.allocated_value,
                        actual_value=total_invoiced,
                        excess=round(excess, 4),
                        currency=vpo.currency,
                    )
                )

        # Client PO over-allocation warnings
        all_client_pos = self.client_po_repo.get_all(limit=10000)
        for cpo in all_client_pos:
            total_allocated = self.mapping_repo.get_total_allocated(cpo.id)
            if total_allocated > cpo.total_value:
                excess = total_allocated - cpo.total_value
                client_po_violations.append(
                    BillingViolation(
                        violation_type="CLIENT_PO_OVER_ALLOCATED",
                        entity_id=cpo.id,
                        entity_ref=cpo.po_number,
                        cap_value=cpo.total_value,
                        actual_value=total_allocated,
                        excess=round(excess, 4),
                        currency=cpo.currency,
                    )
                )

        return BillingViolationsResponse(
            vendor_po_violations=vendor_po_violations,
            client_po_violations=client_po_violations,
            total_violations=len(vendor_po_violations) + len(client_po_violations),
        )
