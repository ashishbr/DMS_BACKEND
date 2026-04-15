"""
RelinkService
-------------
Re-runs all document linking and status advancement on already-processed records.

Use this when:
  - Multiple documents were uploaded at once (wrong processing order)
  - Auto-linking failed during initial classification
  - POAllocation entries are missing for linked VendorPOs
  - Statuses are stuck at DRAFT despite linked invoices existing

Endpoint: POST /api/financial/relink
"""
import uuid
from typing import Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    Document,
    ClientPO,
    VendorPO,
    VendorInvoice,
    ClientInvoice,
    POAllocation,
)
from app.repositories.client_po_repository import ClientPORepository
from app.repositories.vendor_po_repository import VendorPORepository
from app.repositories.po_mapping_repository import POMappingRepository
from app.repositories.vendor_invoice_repository import VendorInvoiceRepository
from app.repositories.client_invoice_repository import ClientInvoiceRepository


class RelinkService:
    def __init__(self, db: Session):
        self.db = db
        self.client_po_repo = ClientPORepository(db)
        self.vendor_po_repo = VendorPORepository(db)
        self.mapping_repo = POMappingRepository(db)
        self.vendor_inv_repo = VendorInvoiceRepository(db)
        self.client_inv_repo = ClientInvoiceRepository(db)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_full_relink(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "vendor_pos_linked": 0,
            "allocations_created": 0,
            "vendor_invoices_linked": 0,
            "client_invoices_linked": 0,
            "statuses_advanced": 0,
            "document_clients_synced": 0,
        }

        stats["vendor_pos_linked"] = self._link_vendor_pos_to_client_pos()
        stats["allocations_created"] = self._create_missing_allocations()
        stats["vendor_invoices_linked"] = self._link_vendor_invoices_to_pos()
        stats["client_invoices_linked"] = self._link_client_invoices_to_pos()
        stats["statuses_advanced"] = self._advance_statuses()
        stats["document_clients_synced"] = self._sync_document_client_fields()

        self.db.commit()
        return stats

    # ------------------------------------------------------------------
    # Step 1: Link unlinked VendorPOs → ClientPOs
    # ------------------------------------------------------------------

    def _link_vendor_pos_to_client_pos(self) -> int:
        """
        For each VendorPO with no client_po_id, try to find its ClientPO via:
        1. The linked Document's client name → exact ClientPO match
        2. VendorPO.vendor_po_number contains a CPO reference (e.g. "CPO-2024-001")
        """
        unlinked = (
            self.db.query(VendorPO)
            .filter(VendorPO.client_po_id.is_(None), VendorPO.is_generated == False)
            .all()
        )
        linked = 0
        for vpo in unlinked:
            cpo = None

            # Strategy 1: vendor_po_number matches a ClientPO's po_number
            # (e.g. both documents reference the same project PO — "PO-2025-101")
            if vpo.vendor_po_number:
                cpo = self.client_po_repo.get_by_po_number(vpo.vendor_po_number)

            # Strategy 2: client name from Document.client or DocumentClientLink
            if not cpo:
                client_name = self._get_client_name_for_vendor_po(vpo)
                if client_name:
                    candidates = self.client_po_repo.get_by_client_name(client_name)
                    if candidates:
                        cpo = (
                            candidates[0]
                            if len(candidates) == 1
                            else self._pick_best_client_po(candidates)
                        )

            if cpo:
                vpo.client_po_id = cpo.id
                self.db.flush()
                linked += 1

        return linked

    def _get_client_name_for_vendor_po(self, vpo: VendorPO) -> str:
        """Resolve client name from the linked Document row or DocumentClientLink."""
        BLANK = {"", "unknown", "unknown client", "unknown vendor", "n/a"}
        if vpo.document_id:
            doc = self.db.query(Document).filter(Document.id == vpo.document_id).first()
            if doc:
                # 1. Direct Document.client field
                if doc.client and doc.client.strip().lower() not in BLANK:
                    return doc.client
                # 2. DocumentClientLink — manual assignment from Document mapper
                from app.models import DocumentClientLink
                link = (
                    self.db.query(DocumentClientLink)
                    .filter(
                        DocumentClientLink.document_id == vpo.document_id,
                        DocumentClientLink.is_active == True,
                    )
                    .first()
                )
                if link and link.client_name and link.client_name.strip().lower() not in BLANK:
                    return link.client_name
        return ""

    def _pick_best_client_po(self, candidates):
        # Prefer ACTIVE, then DRAFT with most recent created_at
        _epoch = datetime(1970, 1, 1)
        active = [c for c in candidates if c.status == "ACTIVE"]
        if active:
            return sorted(active, key=lambda c: c.created_at or _epoch, reverse=True)[0]
        return sorted(candidates, key=lambda c: c.created_at or _epoch, reverse=True)[0]

    # ------------------------------------------------------------------
    # Step 2: Create missing POAllocation rows
    # ------------------------------------------------------------------

    def _create_missing_allocations(self) -> int:
        """
        For every VendorPO that has a client_po_id but no POAllocation entry,
        create the allocation record.
        """
        linked_vpos = (
            self.db.query(VendorPO)
            .filter(VendorPO.client_po_id.isnot(None))
            .all()
        )
        created = 0
        for vpo in linked_vpos:
            existing = self.mapping_repo.get_by_vendor_po(vpo.id)
            if not existing:
                self.mapping_repo.upsert(
                    client_po_id=vpo.client_po_id,
                    vendor_po_id=vpo.id,
                    allocated_value=vpo.allocated_value,
                    currency=vpo.currency or "USD",
                )
                created += 1
        return created

    # ------------------------------------------------------------------
    # Step 3: Link unlinked VendorInvoices → VendorPOs
    # ------------------------------------------------------------------

    def _link_vendor_invoices_to_pos(self) -> int:
        """
        For each VendorInvoice with no vendor_po_id, try to find its VendorPO via:
        1. invoice.vendor_name fuzzy-match on VendorPO.vendor_name (unique)
        2. po_number stored in the linked Document's extracted_json
        """
        unlinked = (
            self.db.query(VendorInvoice)
            .filter(VendorInvoice.vendor_po_id.is_(None))
            .all()
        )
        linked = 0
        for inv in unlinked:
            vpo = self._find_vendor_po_for_invoice(inv)
            if vpo:
                inv.vendor_po_id = vpo.id
                inv.matching_status = "TWO_WAY_MATCHED"
                self.db.flush()
                linked += 1
            else:
                inv.matching_status = "UNMATCHED"
                self.db.flush()

        return linked

    def _find_vendor_po_for_invoice(self, inv: VendorInvoice):
        # 1. Try po_number stored in the source document's extracted JSON
        po_num = self._get_po_number_from_document(inv.document_id)
        if po_num:
            vpo = self.vendor_po_repo.get_by_vendor_po_number(po_num)
            if vpo:
                return vpo

        # 2. Fuzzy vendor name match (unique = safe to auto-link)
        candidates = self.vendor_po_repo.find_by_vendor_name_fuzzy(
            inv.vendor_name, limit=10
        )
        same_currency = [c for c in candidates if c.currency == inv.currency]
        if len(same_currency) == 1:
            return same_currency[0]

        # 3. Exact vendor name (case-insensitive) — pick most recent
        exact = [
            c for c in same_currency
            if c.vendor_name.lower() == inv.vendor_name.lower()
        ]
        if exact:
            return sorted(exact, key=lambda v: v.issue_date or datetime(1970, 1, 1), reverse=True)[0]

        return None

    # ------------------------------------------------------------------
    # Step 4: Link unlinked ClientInvoices → ClientPOs
    # ------------------------------------------------------------------

    def _link_client_invoices_to_pos(self) -> int:
        """
        For each ClientInvoice with no client_po_id, find its ClientPO via:
        1. po_number in the source Document's extracted JSON
        2. client_name → ClientPO.client_name (unique match)
        """
        unlinked = (
            self.db.query(ClientInvoice)
            .filter(ClientInvoice.client_po_id.is_(None))
            .all()
        )
        linked = 0
        for inv in unlinked:
            cpo = self._find_client_po_for_invoice(inv)
            if cpo:
                inv.client_po_id = cpo.id
                self.db.flush()
                linked += 1

        return linked

    def _find_client_po_for_invoice(self, inv: ClientInvoice):
        # 1. PO number from source document
        po_num = self._get_po_number_from_document(inv.document_id)
        if po_num:
            cpo = self.client_po_repo.get_by_po_number(po_num)
            if cpo:
                return cpo

        # 2. Client name match
        if inv.client_name:
            candidates = self.client_po_repo.get_by_client_name(inv.client_name)
            if len(candidates) == 1:
                return candidates[0]
            if candidates:
                return self._pick_best_client_po(candidates)

        return None

    # ------------------------------------------------------------------
    # Step 5: Advance statuses
    # ------------------------------------------------------------------

    def _advance_statuses(self) -> int:
        """
        Advance ClientPO and VendorPO from DRAFT → ACTIVE when they
        have at least one linked invoice.
        """
        advanced = 0

        # VendorPOs: DRAFT → ACTIVE when at least one linked VendorInvoice exists
        draft_vpos = (
            self.db.query(VendorPO)
            .filter(VendorPO.status == "DRAFT")
            .all()
        )
        for vpo in draft_vpos:
            has_invoice = (
                self.db.query(VendorInvoice)
                .filter(VendorInvoice.vendor_po_id == vpo.id)
                .first()
            )
            if has_invoice:
                vpo.status = "ACTIVE"
                self.db.flush()
                advanced += 1

        # ClientPOs: DRAFT → ACTIVE when at least one linked ClientInvoice exists
        draft_cpos = (
            self.db.query(ClientPO)
            .filter(ClientPO.status == "DRAFT")
            .all()
        )
        for cpo in draft_cpos:
            has_invoice = (
                self.db.query(ClientInvoice)
                .filter(ClientInvoice.client_po_id == cpo.id)
                .first()
            )
            if has_invoice:
                cpo.status = "ACTIVE"
                self.db.flush()
                advanced += 1

        return advanced

    # ------------------------------------------------------------------
    # Step 6: Sync Document.client from financial records
    # ------------------------------------------------------------------

    def _get_explicitly_unlinked_doc_ids(self) -> set:
        """
        Return the set of document IDs that were manually unlinked by the user
        and currently have no active override link.  These must be skipped by
        _sync_document_client_fields so that a relink run does not silently
        re-assign the client that the user just removed.
        """
        from app.models import DocumentClientLink

        active_ids = set(
            row[0]
            for row in self.db.query(DocumentClientLink.document_id)
            .filter(DocumentClientLink.is_active == True)
            .all()
        )
        inactive_ids = set(
            row[0]
            for row in self.db.query(DocumentClientLink.document_id)
            .filter(DocumentClientLink.is_active == False)
            .all()
        )
        # Explicitly unlinked = has at least one inactive record but no active one
        return inactive_ids - active_ids

    def _sync_document_client_fields(self) -> int:
        """
        Back-propagate client_name from financial records → Document.client.

        This keeps the Documents tab in sync with the Clients tab.
        Without this step, a ClientInvoice can have client_name = "Acme Corp"
        while its parent Document.client remains blank/Unknown Client, causing
        the document-client-mapper to classify it as UNLINKED even though the
        Clients tab correctly shows it under the right client.

        Handles:
          - ClientInvoice → Document (uses client_name)
          - ClientPO      → Document (uses client_name)
          - VendorPO      → Document (resolves client_name via linked ClientPO)
          - VendorInvoice → Document (resolves client_name via VendorPO → ClientPO)

        Documents that were explicitly unlinked by the user (inactive
        DocumentClientLink, no active override) are skipped so the user's
        action is not silently undone.
        """
        BLANK = {"", "unknown", "unknown client", "unknown vendor", "n/a"}
        synced = 0

        # Pre-fetch doc IDs the user has explicitly unlinked — do not re-assign these.
        explicitly_unlinked = self._get_explicitly_unlinked_doc_ids()

        # Sync from ClientInvoice records
        for inv in self.db.query(ClientInvoice).all():
            if not inv.document_id or not inv.client_name:
                continue
            if inv.client_name.strip().lower() in BLANK:
                continue
            if inv.document_id in explicitly_unlinked:
                continue
            doc = self.db.query(Document).filter(Document.id == inv.document_id).first()
            if doc and (not doc.client or doc.client.strip().lower() in BLANK
                        or doc.client != inv.client_name):
                doc.client = inv.client_name
                self.db.flush()
                synced += 1

        # Sync from ClientPO records
        for cpo in self.db.query(ClientPO).all():
            if not cpo.document_id or not cpo.client_name:
                continue
            if cpo.client_name.strip().lower() in BLANK:
                continue
            if cpo.document_id in explicitly_unlinked:
                continue
            doc = self.db.query(Document).filter(Document.id == cpo.document_id).first()
            if doc and (not doc.client or doc.client.strip().lower() in BLANK
                        or doc.client != cpo.client_name):
                doc.client = cpo.client_name
                self.db.flush()
                synced += 1

        # Sync from VendorPO records that are linked to a ClientPO
        # (resolves client_name via the parent ClientPO)
        for vpo in self.db.query(VendorPO).filter(VendorPO.client_po_id.isnot(None)).all():
            if not vpo.document_id:
                continue
            if vpo.document_id in explicitly_unlinked:
                continue
            cpo = self.db.query(ClientPO).filter(ClientPO.id == vpo.client_po_id).first()
            if not cpo or not cpo.client_name or cpo.client_name.strip().lower() in BLANK:
                continue
            doc = self.db.query(Document).filter(Document.id == vpo.document_id).first()
            if doc and (not doc.client or doc.client.strip().lower() in BLANK
                        or doc.client != cpo.client_name):
                doc.client = cpo.client_name
                self.db.flush()
                synced += 1

        # Sync from VendorInvoice records that are linked to a VendorPO
        # (resolves client_name via VendorPO → ClientPO)
        for vinv in self.db.query(VendorInvoice).filter(VendorInvoice.vendor_po_id.isnot(None)).all():
            if not vinv.document_id:
                continue
            if vinv.document_id in explicitly_unlinked:
                continue
            vpo = self.db.query(VendorPO).filter(VendorPO.id == vinv.vendor_po_id).first()
            if not vpo or not vpo.client_po_id:
                continue
            cpo = self.db.query(ClientPO).filter(ClientPO.id == vpo.client_po_id).first()
            if not cpo or not cpo.client_name or cpo.client_name.strip().lower() in BLANK:
                continue
            doc = self.db.query(Document).filter(Document.id == vinv.document_id).first()
            if doc and (not doc.client or doc.client.strip().lower() in BLANK
                        or doc.client != cpo.client_name):
                doc.client = cpo.client_name
                self.db.flush()
                synced += 1

        return synced

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _get_po_number_from_document(self, document_id: str) -> str:
        """
        Pull po_number from Document.po_number or from extracted_json.
        Invoices often store the referenced PO number in the source document.
        """
        if not document_id:
            return ""

        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return ""

        # Direct field first
        if doc.po_number:
            return doc.po_number

        # Fall back to extracted_json
        if doc.extracted_json:
            import json
            try:
                data = json.loads(doc.extracted_json)
                return (
                    data.get("po_number")
                    or data.get("reference_po_number")
                    or data.get("client_po_number")
                    or ""
                )
            except (json.JSONDecodeError, TypeError):
                pass

        return ""
