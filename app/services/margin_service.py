"""
Margin Service
--------------
Provides real-time margin visibility at the Client PO level.

Margin = ClientPO.total_value - SUM(POAllocation.allocated_value)

All calculations query live data — no caching.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models import ClientPO, VendorPO, VendorInvoice
from app.repositories.client_po_repository import ClientPORepository
from app.repositories.vendor_po_repository import VendorPORepository
from app.repositories.po_mapping_repository import POMappingRepository
from app.repositories.vendor_invoice_repository import VendorInvoiceRepository
from app.schemas import (
    MarginSummary,
    VendorPOWithInvoices,
    ClientPOLineage,
    GlobalMarginSummary,
    ClientPOResponse,
    VendorPOResponse,
    VendorInvoiceResponse,
)


class MarginService:
    def __init__(self, db: Session):
        self.db = db
        self.client_po_repo = ClientPORepository(db)
        self.vendor_po_repo = VendorPORepository(db)
        self.mapping_repo = POMappingRepository(db)
        self.vendor_inv_repo = VendorInvoiceRepository(db)

    # ------------------------------------------------------------------
    # Per-ClientPO margin
    # ------------------------------------------------------------------

    def get_margin(self, client_po_id: str) -> MarginSummary:
        """Calculate margin for a single Client PO."""
        client_po = self.client_po_repo.get(client_po_id)
        if not client_po:
            raise ValueError(f"ClientPO {client_po_id} not found")

        total_allocated = self.mapping_repo.get_total_allocated(client_po_id)
        margin = client_po.total_value - total_allocated
        margin_pct = (margin / client_po.total_value * 100) if client_po.total_value > 0 else 0.0
        vendor_count = len(self.mapping_repo.get_by_client_po(client_po_id))
        over_allocated = total_allocated > client_po.total_value
        over_allocated_by = (total_allocated - client_po.total_value) if over_allocated else None

        return MarginSummary(
            client_po_id=client_po.id,
            po_number=client_po.po_number,
            client_name=client_po.client_name,
            total_value=client_po.total_value,
            total_allocated=total_allocated,
            margin=margin,
            margin_pct=round(margin_pct, 2),
            vendor_count=vendor_count,
            over_allocated=over_allocated,
            over_allocated_by=over_allocated_by,
            currency=client_po.currency,
        )

    def validate_allocation(self, client_po_id: str, new_amount: float) -> Dict[str, Any]:
        """
        Check whether adding new_amount to this ClientPO's allocations would
        exceed the total_value.

        Returns a warning dict — allocations are never hard-blocked.
        """
        client_po = self.client_po_repo.get(client_po_id)
        if not client_po:
            raise ValueError(f"ClientPO {client_po_id} not found")

        current_total = self.mapping_repo.get_total_allocated(client_po_id)
        available = client_po.total_value - current_total
        projected_total = current_total + new_amount
        over_by = max(0.0, projected_total - client_po.total_value)

        return {
            "client_po_id": client_po_id,
            "total_value": client_po.total_value,
            "current_allocated": current_total,
            "new_amount": new_amount,
            "projected_total": projected_total,
            "available": available,
            "warning": over_by > 0,
            "over_by": over_by if over_by > 0 else None,
        }

    # ------------------------------------------------------------------
    # Full lineage
    # ------------------------------------------------------------------

    def get_full_lineage(self, client_po_id: str) -> ClientPOLineage:
        """
        Return the complete financial lineage for a Client PO:
        ClientPO → VendorPO allocations → VendorInvoices
        """
        client_po = self.client_po_repo.get(client_po_id)
        if not client_po:
            raise ValueError(f"ClientPO {client_po_id} not found")

        margin = self.get_margin(client_po_id)
        allocations = self.mapping_repo.get_by_client_po(client_po_id)

        vendor_allocations: List[VendorPOWithInvoices] = []
        for alloc in allocations:
            vendor_po = self.vendor_po_repo.get(alloc.vendor_po_id)
            if not vendor_po:
                continue

            invoices = self.vendor_inv_repo.get_by_vendor_po(vendor_po.id)
            total_invoiced = sum(
                inv.invoice_amount for inv in invoices if not inv.is_duplicate
            )
            remaining = vendor_po.allocated_value - total_invoiced
            utilization_pct = (
                (total_invoiced / vendor_po.allocated_value * 100)
                if vendor_po.allocated_value > 0
                else 0.0
            )

            vendor_allocations.append(
                VendorPOWithInvoices(
                    vendor_po=VendorPOResponse.model_validate(vendor_po),
                    allocated_value=alloc.allocated_value,
                    total_invoiced=total_invoiced,
                    remaining=remaining,
                    utilization_pct=round(utilization_pct, 2),
                    invoices=[VendorInvoiceResponse.model_validate(inv) for inv in invoices],
                )
            )

        return ClientPOLineage(
            client_po=ClientPOResponse.model_validate(client_po),
            margin=margin,
            vendor_allocations=vendor_allocations,
        )

    def get_lineage_by_document(self, document_id: str) -> Optional[ClientPOLineage]:
        """Trace lineage starting from any document_id."""
        client_po = self.client_po_repo.get_by_document_id(document_id)
        if client_po:
            return self.get_full_lineage(client_po.id)

        # Check if it's a VendorPO document
        vendor_po = self.vendor_po_repo.get_by_document_id(document_id)
        if vendor_po and vendor_po.client_po_id:
            return self.get_full_lineage(vendor_po.client_po_id)

        # Check if it's a VendorInvoice document
        vendor_inv = self.vendor_inv_repo.get_by_document_id(document_id)
        if vendor_inv and vendor_inv.vendor_po_id:
            vendor_po = self.vendor_po_repo.get(vendor_inv.vendor_po_id)
            if vendor_po and vendor_po.client_po_id:
                return self.get_full_lineage(vendor_po.client_po_id)

        return None

    # ------------------------------------------------------------------
    # Global summary
    # ------------------------------------------------------------------

    def get_all_margins(self) -> GlobalMarginSummary:
        """Aggregate margin across all Client POs."""
        all_client_pos = self.client_po_repo.get_all_with_margin(limit=10000)
        summaries: List[MarginSummary] = []
        total_revenue = 0.0
        total_cost = 0.0

        for cpo in all_client_pos:
            summary = self.get_margin(cpo.id)
            summaries.append(summary)
            total_revenue += cpo.total_value
            total_cost += summary.total_allocated

        total_margin = total_revenue - total_cost
        overall_pct = (total_margin / total_revenue * 100) if total_revenue > 0 else 0.0
        over_allocated_count = sum(1 for s in summaries if s.over_allocated)

        return GlobalMarginSummary(
            client_pos=summaries,
            total_revenue_committed=total_revenue,
            total_cost_allocated=total_cost,
            total_margin=total_margin,
            overall_margin_pct=round(overall_pct, 2),
            over_allocated_pos=over_allocated_count,
        )
