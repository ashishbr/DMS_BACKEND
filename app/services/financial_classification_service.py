"""
Financial Classification Service
---------------------------------
Orchestrates the final step of the document ingestion pipeline.

After a document is saved to the `documents` table and classified, this
service parses the extracted data and creates the corresponding financial
record in the appropriate specialized table:

  Client PO      → client_pos
  Vendor PO      → vendor_pos
  Client Invoice → client_invoices  (+ auto-link to ClientPO if found)
  Vendor Invoice → vendor_invoices  (+ 2-way/3-way match + overbilling check)

All records maintain a document_id FK back to the originating document.
"""
import uuid
import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.models import Document, ClientPO, VendorPO, ClientInvoice, VendorInvoice
from app.repositories.client_po_repository import ClientPORepository
from app.repositories.vendor_po_repository import VendorPORepository
from app.repositories.client_invoice_repository import ClientInvoiceRepository
from app.repositories.vendor_invoice_repository import VendorInvoiceRepository


# Processing status constants
class ProcessingStatus:
    UPLOADED = "UPLOADED"
    EXTRACTED = "EXTRACTED"
    CLASSIFIED = "CLASSIFIED"
    PARSED = "PARSED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"


class FinancialClassificationService:
    def __init__(self, db: Session):
        self.db = db
        self.client_po_repo = ClientPORepository(db)
        self.vendor_po_repo = VendorPORepository(db)
        self.client_inv_repo = ClientInvoiceRepository(db)
        self.vendor_inv_repo = VendorInvoiceRepository(db)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def classify_and_create(
        self,
        document: Document,
        extracted_data: Dict[str, Any],
    ) -> Optional[Any]:
        """
        Inspect document.category and create the appropriate financial record.
        Returns the created financial record, or None if category is not handled
        (e.g. Service Agreement — handled by the MSA system).

        Updates document.processing_status to VALIDATED or FAILED.
        """
        category = (document.category or "").strip()

        try:
            record = None
            if category == "Client PO":
                record = self._create_client_po(document, extracted_data)
            elif category == "Vendor PO":
                record = self._create_vendor_po(document, extracted_data)
            elif category == "Client Invoice":
                record = self._create_client_invoice(document, extracted_data)
            elif category == "Vendor Invoice":
                record = self._create_vendor_invoice(document, extracted_data)
            else:
                # Service Agreement and Unknown — no financial record needed here
                document.processing_status = ProcessingStatus.VALIDATED
                self.db.flush()
                return None

            document.processing_status = ProcessingStatus.VALIDATED
            self.db.flush()
            return record

        except Exception as exc:
            document.processing_status = ProcessingStatus.FAILED
            try:
                self.db.flush()
            except Exception:
                pass
            print(f"[FinancialClassificationService] ERROR for doc {document.id}: {exc}")
            raise

    # ------------------------------------------------------------------
    # Private creators
    # ------------------------------------------------------------------

    def _create_client_po(
        self, document: Document, data: Dict[str, Any]
    ) -> ClientPO:
        # Avoid duplicate if document_id already has a ClientPO record
        existing = self.client_po_repo.get_by_document_id(document.id)
        if existing:
            return existing

        po_number = (
            data.get("po_number")
            or document.po_number
            or f"CPO-{document.id[:8].upper()}"
        )

        client_po = ClientPO(
            id=str(uuid.uuid4()),
            document_id=document.id,
            po_number=po_number,
            client_name=data.get("client") or document.client or "Unknown Client",
            total_value=float(data.get("amount") or document.amount or 0.0),
            currency=data.get("currency") or document.currency or "USD",
            service_scope=data.get("summary") or data.get("key_terms"),
            issue_date=self._parse_date(data.get("date")),
            start_date=self._parse_date(data.get("date")),
            end_date=self._parse_date(data.get("due_date")),
            status="DRAFT",
            msa_number=data.get("msa_number") or document.msa_number,
        )
        return self.client_po_repo.create(client_po)

    def _create_vendor_po(
        self, document: Document, data: Dict[str, Any]
    ) -> VendorPO:
        existing = self.vendor_po_repo.get_by_document_id(document.id)
        if existing:
            return existing

        vendor_po_number = (
            data.get("po_number")
            or document.po_number
            or f"VPO-{document.id[:8].upper()}"
        )

        # Attempt to auto-link to a ClientPO using the MSA number or client match
        client_po_id = self._find_client_po_for_vendor_po(data, document)

        vendor_po = VendorPO(
            id=str(uuid.uuid4()),
            document_id=document.id,
            vendor_po_number=vendor_po_number,
            vendor_name=data.get("vendor") or document.vendor or "Unknown Vendor",
            client_po_id=client_po_id,
            allocated_value=float(data.get("amount") or document.amount or 0.0),
            currency=data.get("currency") or document.currency or "USD",
            service_description=data.get("summary"),
            issue_date=self._parse_date(data.get("date")),
            start_date=self._parse_date(data.get("date")),
            end_date=self._parse_date(data.get("due_date")),
            status="DRAFT",
        )
        return self.vendor_po_repo.create(vendor_po)

    def _create_client_invoice(
        self, document: Document, data: Dict[str, Any]
    ) -> ClientInvoice:
        existing = self.client_inv_repo.get_by_document_id(document.id)
        if existing:
            return existing

        invoice_number = (
            data.get("invoice_number")
            or document.invoice_number
            or f"CINV-{document.id[:8].upper()}"
        )

        # Auto-link to ClientPO
        client_po_id = self._find_client_po_for_invoice(data, document)

        invoice = ClientInvoice(
            id=str(uuid.uuid4()),
            document_id=document.id,
            client_po_id=client_po_id,
            invoice_number=invoice_number,
            client_name=data.get("client") or document.client or "Unknown Client",
            invoice_amount=float(data.get("amount") or document.amount or 0.0),
            currency=data.get("currency") or document.currency or "USD",
            invoice_date=self._parse_date(data.get("date")),
            due_date=self._parse_date(data.get("due_date")),
            status="PENDING",
        )
        return self.client_inv_repo.create(invoice)

    def _create_vendor_invoice(
        self, document: Document, data: Dict[str, Any]
    ) -> VendorInvoice:
        existing = self.vendor_inv_repo.get_by_document_id(document.id)
        if existing:
            return existing

        invoice_number = (
            data.get("invoice_number")
            or document.invoice_number
            or f"VINV-{document.id[:8].upper()}"
        )

        # Auto-link to VendorPO
        vendor_po_id = self._find_vendor_po_for_invoice(data, document)

        # Parse optional 3-way matching fields
        unit_rate = self._safe_float(data.get("unit_rate"))
        quantity = self._safe_float(data.get("quantity"))

        invoice = VendorInvoice(
            id=str(uuid.uuid4()),
            document_id=document.id,
            vendor_po_id=vendor_po_id,
            invoice_number=invoice_number,
            vendor_name=data.get("vendor") or document.vendor or "Unknown Vendor",
            invoice_amount=float(data.get("amount") or document.amount or 0.0),
            currency=data.get("currency") or document.currency or "USD",
            invoice_date=self._parse_date(data.get("date")),
            due_date=self._parse_date(data.get("due_date")),
            unit_rate=unit_rate,
            quantity=quantity,
            status="PENDING",
            matching_status="UNMATCHED" if not vendor_po_id else None,
        )
        created = self.vendor_inv_repo.create(invoice)

        # Run matching + overbilling in the same transaction (deferred to services)
        # The services are called from UploadService after this method returns.
        return created

    # ------------------------------------------------------------------
    # Auto-linking helpers
    # ------------------------------------------------------------------

    def _find_client_po_for_vendor_po(
        self, data: Dict[str, Any], document: Document
    ) -> Optional[str]:
        """Try to match a Vendor PO to an existing Client PO."""
        # 1. By explicit PO number reference in extracted data
        ref_po = data.get("client_po_number") or data.get("reference_po_number")
        if ref_po:
            cpo = self.client_po_repo.get_by_po_number(ref_po)
            if cpo:
                return cpo.id

        # 2. By client name + msa_number
        msa = data.get("msa_number") or document.msa_number
        client = data.get("client") or document.client
        if client:
            candidates = self.client_po_repo.get_by_client_name(client)
            if msa:
                for cpo in candidates:
                    if cpo.msa_number and cpo.msa_number == msa:
                        return cpo.id
            if len(candidates) == 1:
                return candidates[0].id

        return None

    def _find_client_po_for_invoice(
        self, data: Dict[str, Any], document: Document
    ) -> Optional[str]:
        """Auto-link a Client Invoice to a Client PO."""
        # 1. Exact PO number
        po_num = data.get("po_number") or document.po_number
        if po_num:
            cpo = self.client_po_repo.get_by_po_number(po_num)
            if cpo:
                return cpo.id

        # 2. Client name (unique match)
        client = data.get("client") or document.client
        if client:
            candidates = self.client_po_repo.get_by_client_name(client)
            if len(candidates) == 1:
                return candidates[0].id

        return None

    def _find_vendor_po_for_invoice(
        self, data: Dict[str, Any], document: Document
    ) -> Optional[str]:
        """Auto-link a Vendor Invoice to a Vendor PO."""
        # 1. Exact PO number
        po_num = data.get("po_number") or document.po_number
        if po_num:
            vpo = self.vendor_po_repo.get_by_vendor_po_number(po_num)
            if vpo:
                return vpo.id

        # 2. Vendor name (unique match)
        vendor = data.get("vendor") or document.vendor
        if vendor:
            candidates = self.vendor_po_repo.get_by_vendor_name(vendor)
            if len(candidates) == 1:
                return candidates[0].id

        return None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            for fmt in [
                "%Y-%m-%d",
                "%d %b %Y",
                "%d/%m/%Y",
                "%m/%d/%Y",
                "%Y-%m-%dT%H:%M:%S",
            ]:
                try:
                    return datetime.strptime(value.split("T")[0].split()[0], fmt)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None
