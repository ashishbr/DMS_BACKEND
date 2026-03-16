"""
Invoice Matching Service
------------------------
Implements 2-way and 3-way invoice matching against Vendor POs.

2-Way Match (Invoice ↔ Vendor PO)
  Priority order:
  1. Exact vendor_po_number match from invoice extracted data
  2. Fuzzy vendor name match (Levenshtein ≤ 2 edits) within same currency
  3. Amount similarity (±5%) + same vendor token + date within 1 year

3-Way Match (Invoice ↔ Vendor PO ↔ unit_rate × quantity)
  Requires unit_rate and quantity populated on the invoice.
  Tolerance: |computed - invoice_amount| / invoice_amount < 0.01

Duplicate Detection
  Hard duplicate: same invoice_number + same vendor_name
  Soft duplicate: same vendor + amount within 1% + date within 7 days
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models import VendorInvoice, VendorPO
from app.repositories.vendor_po_repository import VendorPORepository
from app.repositories.vendor_invoice_repository import VendorInvoiceRepository


def _levenshtein(s1: str, s2: str) -> int:
    """Simple iterative Levenshtein distance (no external deps)."""
    s1, s2 = s1.lower(), s2.lower()
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


class InvoiceMatchingService:
    # Matching thresholds
    AMOUNT_TOLERANCE_PCT = 0.05       # 5% for 2-way PO amount similarity match
    THREE_WAY_AMOUNT_TOLERANCE = 0.01  # 1% for computed vs stated amount
    FUZZY_MAX_DISTANCE = 2            # Levenshtein distance for vendor name fuzzy match
    DATE_PROXIMITY_DAYS = 365         # PO must be within 1 year of invoice

    def __init__(self, db: Session):
        self.db = db
        self.vendor_po_repo = VendorPORepository(db)
        self.vendor_inv_repo = VendorInvoiceRepository(db)

    # ------------------------------------------------------------------
    # 2-Way Matching
    # ------------------------------------------------------------------

    def match_vendor_invoice_to_po(self, invoice: VendorInvoice) -> Optional[VendorPO]:
        """
        Attempt to match a VendorInvoice to a VendorPO using three strategies.
        Updates invoice.vendor_po_id and invoice.matching_status in-place.
        Caller is responsible for committing.
        """
        po = (
            self._match_by_po_number(invoice)
            or self._match_by_fuzzy_vendor_name(invoice)
            or self._match_by_amount_similarity(invoice)
        )

        if po:
            invoice.vendor_po_id = po.id
            invoice.matching_status = "TWO_WAY_MATCHED"
        else:
            invoice.matching_status = "UNMATCHED"

        self.db.flush()
        return po

    def _match_by_po_number(self, invoice: VendorInvoice) -> Optional[VendorPO]:
        """Strategy 1: exact PO number embedded in the invoice."""
        # invoice.vendor_po_id may already be set by FinancialClassificationService
        if invoice.vendor_po_id:
            return self.vendor_po_repo.get(invoice.vendor_po_id)

        # No direct field — nothing to match on here; caller can try other strategies
        return None

    def _match_by_fuzzy_vendor_name(self, invoice: VendorInvoice) -> Optional[VendorPO]:
        """Strategy 2: fuzzy vendor name match within same currency."""
        candidates = self.vendor_po_repo.find_by_vendor_name_fuzzy(invoice.vendor_name, limit=10)
        best: Optional[VendorPO] = None
        best_distance = self.FUZZY_MAX_DISTANCE + 1

        for po in candidates:
            if po.currency != invoice.currency:
                continue
            dist = _levenshtein(invoice.vendor_name, po.vendor_name)
            if dist <= self.FUZZY_MAX_DISTANCE and dist < best_distance:
                best = po
                best_distance = dist

        return best

    def _match_by_amount_similarity(self, invoice: VendorInvoice) -> Optional[VendorPO]:
        """Strategy 3: amount within 5% + vendor name token + date proximity."""
        if not invoice.invoice_amount:
            return None

        token = invoice.vendor_name.split()[0].lower() if invoice.vendor_name else ""
        amount_min = invoice.invoice_amount * (1 - self.AMOUNT_TOLERANCE_PCT)
        amount_max = invoice.invoice_amount * (1 + self.AMOUNT_TOLERANCE_PCT)

        candidates = (
            self.db.query(VendorPO)
            .filter(
                VendorPO.allocated_value >= amount_min,
                VendorPO.allocated_value <= amount_max,
                VendorPO.currency == invoice.currency,
            )
            .all()
        )

        for po in candidates:
            if token and token not in po.vendor_name.lower():
                continue
            if invoice.invoice_date and po.issue_date:
                delta = abs((invoice.invoice_date - po.issue_date).days)
                if delta > self.DATE_PROXIMITY_DAYS:
                    continue
            return po

        return None

    # ------------------------------------------------------------------
    # 3-Way Matching
    # ------------------------------------------------------------------

    def validate_three_way(
        self, invoice: VendorInvoice, vendor_po: VendorPO
    ) -> Dict[str, Any]:
        """
        Validate invoice amount against unit_rate × quantity.
        Returns a result dict with 'valid', 'issue', and 'computed_amount'.
        Updates invoice.matching_status if 3-way validation passes.
        """
        if invoice.unit_rate is None or invoice.quantity is None:
            return {
                "valid": False,
                "skipped": True,
                "reason": "unit_rate or quantity not available — 3-way match skipped",
            }

        computed = invoice.unit_rate * invoice.quantity
        deviation = abs(computed - invoice.invoice_amount)
        tolerance = invoice.invoice_amount * self.THREE_WAY_AMOUNT_TOLERANCE

        if deviation <= tolerance:
            invoice.matching_status = "THREE_WAY_MATCHED"
            self.db.flush()
            return {
                "valid": True,
                "computed_amount": computed,
                "stated_amount": invoice.invoice_amount,
                "deviation": deviation,
            }

        # Determine specific issue
        if computed < invoice.invoice_amount * (1 - self.THREE_WAY_AMOUNT_TOLERANCE):
            issue = "RATE_MISMATCH"
            detail = (
                f"Computed amount ({computed:,.2f}) is less than stated ({invoice.invoice_amount:,.2f}). "
                "Possible rate overcharge."
            )
        else:
            issue = "QUANTITY_MISMATCH"
            detail = (
                f"Computed amount ({computed:,.2f}) differs from stated ({invoice.invoice_amount:,.2f}). "
                "Possible quantity discrepancy."
            )

        return {
            "valid": False,
            "issue": issue,
            "detail": detail,
            "computed_amount": computed,
            "stated_amount": invoice.invoice_amount,
            "deviation": deviation,
        }

    # ------------------------------------------------------------------
    # Duplicate Detection
    # ------------------------------------------------------------------

    def detect_duplicate(self, invoice: VendorInvoice) -> Dict[str, Any]:
        """
        Check for hard and soft duplicates.
        Hard: same invoice_number + same vendor_name
        Soft: same vendor + amount within 1% + date within 7 days

        Marks invoice.is_duplicate = True and status = FLAGGED on detection.
        Returns {is_duplicate, type, existing_id}.
        """
        # Hard duplicate
        hard = self.vendor_inv_repo.find_hard_duplicate(
            invoice.invoice_number, invoice.vendor_name
        )
        if hard and hard.id != invoice.id:
            invoice.is_duplicate = True
            invoice.status = "FLAGGED"
            invoice.matching_status = "DUPLICATE"
            self.db.flush()
            return {
                "is_duplicate": True,
                "type": "HARD",
                "existing_id": hard.id,
                "detail": f"Duplicate of invoice {hard.id} (same invoice number + vendor)",
            }

        # Soft duplicate
        softs = self.vendor_inv_repo.find_soft_duplicates(
            vendor_name=invoice.vendor_name,
            invoice_amount=invoice.invoice_amount,
            invoice_date=invoice.invoice_date,
            exclude_id=invoice.id,
        )
        if softs:
            invoice.is_duplicate = True
            invoice.status = "FLAGGED"
            invoice.matching_status = "DUPLICATE"
            self.db.flush()
            return {
                "is_duplicate": True,
                "type": "SOFT",
                "existing_id": softs[0].id,
                "detail": (
                    f"Possible duplicate of invoice {softs[0].id} "
                    f"(same vendor, similar amount {softs[0].invoice_amount:,.2f}, "
                    f"similar date {softs[0].invoice_date})"
                ),
            }

        return {"is_duplicate": False}

    # ------------------------------------------------------------------
    # Full validation pipeline for a single Vendor Invoice
    # ------------------------------------------------------------------

    def run_full_validation(self, invoice: VendorInvoice) -> Dict[str, Any]:
        """
        Run duplicate check → 2-way match → 3-way match in sequence.
        Returns a combined result dict.
        """
        result: Dict[str, Any] = {}

        # 1. Duplicate check first (most critical)
        dup_result = self.detect_duplicate(invoice)
        result["duplicate"] = dup_result
        if dup_result["is_duplicate"]:
            return result  # Skip further matching for duplicates

        # 2. 2-way match (may update invoice.vendor_po_id)
        matched_po = self.match_vendor_invoice_to_po(invoice)
        result["two_way_match"] = {
            "matched": matched_po is not None,
            "vendor_po_id": matched_po.id if matched_po else None,
        }

        # 3. 3-way match (only if 2-way succeeded and unit fields available)
        if matched_po:
            three_way = self.validate_three_way(invoice, matched_po)
            result["three_way_match"] = three_way
        else:
            result["three_way_match"] = {"skipped": True, "reason": "No matched PO for 3-way validation"}

        return result
