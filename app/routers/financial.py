"""
Financial Router  (/api/financial)
------------------------------------
HTTP layer only — no business logic here.
All logic delegated to service layer.

Endpoints:
  Client POs   → /client-pos
  Vendor POs   → /vendor-pos
  Allocations  → /po-allocations   (Layer 2)
  Vendor Inv   → /vendor-invoices
  Client Inv   → /client-invoices
  Reports      → /billing-violations, /margin-summary, /lineage/{document_id}
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ClientPO, VendorPO, ClientInvoice, VendorInvoice
from app.repositories.client_po_repository import ClientPORepository
from app.repositories.vendor_po_repository import VendorPORepository
from app.repositories.po_mapping_repository import POMappingRepository
from app.repositories.vendor_invoice_repository import VendorInvoiceRepository
from app.repositories.client_invoice_repository import ClientInvoiceRepository
from app.services.margin_service import MarginService
from app.services.billing_validation_service import BillingValidationService
from app.services.invoice_matching_service import InvoiceMatchingService
from app.services.alert_generator import AlertGenerator
from app.schemas import (
    ClientPOCreate, ClientPOUpdate, ClientPOResponse,
    VendorPOCreate, VendorPOUpdate, VendorPOResponse,
    POAllocationCreate, POAllocationUpdate, POAllocationResponse, POAllocationWithWarning,
    VendorInvoiceCreate, VendorInvoiceUpdate, VendorInvoiceResponse,
    ClientInvoiceCreate, ClientInvoiceUpdate, ClientInvoiceResponse,
    MarginSummary, ClientPOLineage,
    VendorPOConsumption, BillingViolationsResponse, GlobalMarginSummary,
    VendorWithInvoices, ClientWithVendors, ClientsOverviewResponse,
)

router = APIRouter(prefix="/api/financial", tags=["financial"])


# ---------------------------------------------------------------------------
# CLIENT POs
# ---------------------------------------------------------------------------

@router.get("/client-pos", response_model=GlobalMarginSummary)
async def list_client_pos(db: Session = Depends(get_db)):
    """List all Client POs with margin summary for each."""
    try:
        return MarginService(db).get_all_margins()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/client-pos", response_model=ClientPOResponse, status_code=201)
async def create_client_po(payload: ClientPOCreate, db: Session = Depends(get_db)):
    """Manually create a Client PO (e.g., when auto-classification was skipped)."""
    try:
        repo = ClientPORepository(db)
        if repo.get_by_po_number(payload.po_number):
            raise HTTPException(status_code=409, detail=f"PO number '{payload.po_number}' already exists")

        cpo = ClientPO(id=str(uuid.uuid4()), **payload.model_dump())
        created = repo.create(cpo)
        db.commit()
        return created
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client-pos/{client_po_id}", response_model=ClientPOResponse)
async def get_client_po(client_po_id: str, db: Session = Depends(get_db)):
    record = ClientPORepository(db).get(client_po_id)
    if not record:
        raise HTTPException(status_code=404, detail="Client PO not found")
    return record


@router.put("/client-pos/{client_po_id}", response_model=ClientPOResponse)
async def update_client_po(
    client_po_id: str, payload: ClientPOUpdate, db: Session = Depends(get_db)
):
    try:
        repo = ClientPORepository(db)
        updated = repo.update(client_po_id, payload.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Client PO not found")
        db.commit()

        # Refresh utilization alerts for the linked document
        try:
            from app.models import Document
            doc = db.query(Document).filter(Document.id == updated.document_id).first()
            if doc:
                AlertGenerator(db).generate_alerts_for_document(doc)
                db.commit()
        except Exception:
            db.rollback()

        return updated
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client-pos/{client_po_id}/margin", response_model=MarginSummary)
async def get_client_po_margin(client_po_id: str, db: Session = Depends(get_db)):
    """Real-time margin for a single Client PO."""
    try:
        return MarginService(db).get_margin(client_po_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client-pos/{client_po_id}/lineage", response_model=ClientPOLineage)
async def get_client_po_lineage(client_po_id: str, db: Session = Depends(get_db)):
    """Full lineage: Client PO → Vendor PO allocations → Vendor Invoices."""
    try:
        return MarginService(db).get_full_lineage(client_po_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# VENDOR POs
# ---------------------------------------------------------------------------

@router.get("/vendor-pos", response_model=List[VendorPOResponse])
async def list_vendor_pos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return VendorPORepository(db).get_all(skip=skip, limit=limit)


@router.post("/vendor-pos", response_model=VendorPOResponse, status_code=201)
async def create_vendor_po(payload: VendorPOCreate, db: Session = Depends(get_db)):
    try:
        repo = VendorPORepository(db)
        vpo = VendorPO(id=str(uuid.uuid4()), **payload.model_dump())
        created = repo.create(vpo)
        db.commit()
        return created
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vendor-pos/unlinked", response_model=List[VendorPOResponse])
async def get_unlinked_vendor_pos(db: Session = Depends(get_db)):
    """Vendor POs not yet linked to any Client PO."""
    return VendorPORepository(db).get_unlinked()


@router.get("/vendor-pos/{vendor_po_id}", response_model=VendorPOResponse)
async def get_vendor_po(vendor_po_id: str, db: Session = Depends(get_db)):
    record = VendorPORepository(db).get(vendor_po_id)
    if not record:
        raise HTTPException(status_code=404, detail="Vendor PO not found")
    return record


@router.put("/vendor-pos/{vendor_po_id}", response_model=VendorPOResponse)
async def update_vendor_po(
    vendor_po_id: str, payload: VendorPOUpdate, db: Session = Depends(get_db)
):
    try:
        repo = VendorPORepository(db)
        updated = repo.update(vendor_po_id, payload.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Vendor PO not found")
        db.commit()

        # Re-run billing check + refresh alerts for the linked document
        try:
            BillingValidationService(db).check_vendor_po_overbilling(vendor_po_id)
            from app.models import Document
            doc = db.query(Document).filter(Document.id == updated.document_id).first()
            if doc:
                AlertGenerator(db).generate_alerts_for_document(doc)
            db.commit()
        except Exception:
            db.rollback()

        return updated
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vendor-pos/{vendor_po_id}/consumption", response_model=VendorPOConsumption)
async def get_vendor_po_consumption(vendor_po_id: str, db: Session = Depends(get_db)):
    """Invoice consumption vs allocated cap for a Vendor PO."""
    try:
        return BillingValidationService(db).check_vendor_po_overbilling(vendor_po_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# PO ALLOCATIONS  (Layer 2 — EMB Mapping)
# ---------------------------------------------------------------------------

@router.get("/po-allocations", response_model=List[POAllocationResponse])
async def list_po_allocations(
    client_po_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    repo = POMappingRepository(db)
    if client_po_id:
        return repo.get_by_client_po(client_po_id)
    return repo.get_all()


@router.post("/po-allocations", response_model=POAllocationWithWarning, status_code=201)
async def create_po_allocation(payload: POAllocationCreate, db: Session = Depends(get_db)):
    """
    Create or update a Client PO → Vendor PO allocation.
    Never blocks — returns a warning if total allocations exceed ClientPO.total_value.
    """
    try:
        margin_svc = MarginService(db)
        billing_svc = BillingValidationService(db)
        mapping_repo = POMappingRepository(db)

        # Validate that both entities exist
        client_po = ClientPORepository(db).get(payload.client_po_id)
        if not client_po:
            raise HTTPException(status_code=404, detail="Client PO not found")
        vendor_po = VendorPORepository(db).get(payload.vendor_po_id)
        if not vendor_po:
            raise HTTPException(status_code=404, detail="Vendor PO not found")

        # Pre-allocation warning check (before flush)
        validation = margin_svc.validate_allocation(payload.client_po_id, payload.allocated_value)
        available_before = validation["available"]

        # Upsert the mapping
        allocation = mapping_repo.upsert(
            client_po_id=payload.client_po_id,
            vendor_po_id=payload.vendor_po_id,
            allocated_value=payload.allocated_value,
            currency=payload.currency,
            service_component=payload.service_component,
            notes=payload.notes,
        )

        # Link vendor_po → client_po if not already linked
        if not vendor_po.client_po_id:
            vendor_po.client_po_id = payload.client_po_id
            db.flush()

        db.commit()

        # Post-allocation actual total
        total_after = mapping_repo.get_total_allocated(payload.client_po_id)
        warning = total_after > client_po.total_value
        over_by = (total_after - client_po.total_value) if warning else None

        return POAllocationWithWarning(
            allocation=POAllocationResponse.model_validate(allocation),
            warning=warning,
            over_allocated_by=over_by,
            available_before=available_before,
            total_allocated_after=total_after,
            client_po_total_value=client_po.total_value,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/po-allocations/{allocation_id}", response_model=POAllocationResponse)
async def update_po_allocation(
    allocation_id: str, payload: POAllocationUpdate, db: Session = Depends(get_db)
):
    try:
        repo = POMappingRepository(db)
        updated = repo.update(allocation_id, payload.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Allocation not found")
        db.commit()
        return updated
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/po-allocations/{allocation_id}", status_code=204)
async def delete_po_allocation(allocation_id: str, db: Session = Depends(get_db)):
    try:
        success = POMappingRepository(db).delete(allocation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Allocation not found")
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# VENDOR INVOICES
# ---------------------------------------------------------------------------

@router.get("/vendor-invoices", response_model=List[VendorInvoiceResponse])
async def list_vendor_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return VendorInvoiceRepository(db).get_all(skip=skip, limit=limit)


@router.get("/vendor-invoices/unlinked", response_model=List[VendorInvoiceResponse])
async def get_unlinked_vendor_invoices(db: Session = Depends(get_db)):
    """Vendor invoices with no Vendor PO link."""
    return VendorInvoiceRepository(db).get_unlinked()


@router.get("/vendor-invoices/{invoice_id}", response_model=VendorInvoiceResponse)
async def get_vendor_invoice(invoice_id: str, db: Session = Depends(get_db)):
    record = VendorInvoiceRepository(db).get(invoice_id)
    if not record:
        raise HTTPException(status_code=404, detail="Vendor invoice not found")
    return record


@router.post("/vendor-invoices", response_model=VendorInvoiceResponse, status_code=201)
async def create_vendor_invoice(payload: VendorInvoiceCreate, db: Session = Depends(get_db)):
    try:
        inv = VendorInvoice(id=str(uuid.uuid4()), **payload.model_dump())
        repo = VendorInvoiceRepository(db)
        created = repo.create(inv)

        # Run full matching + overbilling check
        matching_svc = InvoiceMatchingService(db)
        matching_svc.run_full_validation(created)

        if created.vendor_po_id:
            BillingValidationService(db).check_vendor_po_overbilling(created.vendor_po_id)

        db.commit()
        return created
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/vendor-invoices/{invoice_id}/link", response_model=VendorInvoiceResponse)
async def link_vendor_invoice_to_po(
    invoice_id: str,
    vendor_po_id: str = Query(..., description="ID of the Vendor PO to link"),
    db: Session = Depends(get_db),
):
    """Manually link an unlinked Vendor Invoice to a Vendor PO, then run overbilling check."""
    try:
        repo = VendorInvoiceRepository(db)
        invoice = repo.get(invoice_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Vendor invoice not found")

        vendor_po = VendorPORepository(db).get(vendor_po_id)
        if not vendor_po:
            raise HTTPException(status_code=404, detail="Vendor PO not found")

        invoice.vendor_po_id = vendor_po_id
        invoice.matching_status = "TWO_WAY_MATCHED"
        db.flush()

        # Run 3-way match and overbilling check
        matching_svc = InvoiceMatchingService(db)
        matching_svc.validate_three_way(invoice, vendor_po)
        BillingValidationService(db).check_vendor_po_overbilling(vendor_po_id)

        db.commit()
        db.refresh(invoice)
        return invoice
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/vendor-invoices/{invoice_id}", response_model=VendorInvoiceResponse)
async def update_vendor_invoice(
    invoice_id: str, payload: VendorInvoiceUpdate, db: Session = Depends(get_db)
):
    try:
        repo = VendorInvoiceRepository(db)
        updated = repo.update(invoice_id, payload.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Vendor invoice not found")
        db.commit()

        # Re-run matching + billing check after any update
        try:
            InvoiceMatchingService(db).run_full_validation(updated)
            if updated.vendor_po_id:
                BillingValidationService(db).check_vendor_po_overbilling(updated.vendor_po_id)
            db.commit()
        except Exception:
            db.rollback()

        db.refresh(updated)
        return updated
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# CLIENT INVOICES
# ---------------------------------------------------------------------------

@router.get("/client-invoices", response_model=List[ClientInvoiceResponse])
async def list_client_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return ClientInvoiceRepository(db).get_all(skip=skip, limit=limit)


@router.get("/client-invoices/{invoice_id}", response_model=ClientInvoiceResponse)
async def get_client_invoice(invoice_id: str, db: Session = Depends(get_db)):
    record = ClientInvoiceRepository(db).get(invoice_id)
    if not record:
        raise HTTPException(status_code=404, detail="Client invoice not found")
    return record


@router.post("/client-invoices", response_model=ClientInvoiceResponse, status_code=201)
async def create_client_invoice(payload: ClientInvoiceCreate, db: Session = Depends(get_db)):
    try:
        inv = ClientInvoice(id=str(uuid.uuid4()), **payload.model_dump())
        created = ClientInvoiceRepository(db).create(inv)

        # Auto-advance ClientPO to ACTIVE on first linked invoice
        if created.client_po_id:
            cpo = ClientPORepository(db).get(created.client_po_id)
            if cpo and cpo.status == "DRAFT":
                cpo.status = "ACTIVE"
                db.flush()

        db.commit()

        # Refresh alerts for the linked document
        try:
            from app.models import Document
            doc = db.query(Document).filter(Document.id == created.document_id).first()
            if doc:
                AlertGenerator(db).generate_alerts_for_document(doc)
                db.commit()
        except Exception:
            db.rollback()

        return created
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/client-invoices/{invoice_id}", response_model=ClientInvoiceResponse)
async def update_client_invoice(
    invoice_id: str, payload: ClientInvoiceUpdate, db: Session = Depends(get_db)
):
    try:
        repo = ClientInvoiceRepository(db)
        updated = repo.update(invoice_id, payload.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Client invoice not found")
        db.commit()
        return updated
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# CLIENTS OVERVIEW  (hierarchical: client → vendors → invoices)
# ---------------------------------------------------------------------------

@router.get("/clients-overview", response_model=ClientsOverviewResponse)
async def get_clients_overview(db: Session = Depends(get_db)):
    """
    Returns every client with their associated vendors and invoices.

    Structure:
      clients[]
        client_name, total_po_value, total_client_invoiced
        client_pos[]
        client_invoices[]
        vendors[]
          vendor_name, total_allocated, total_invoiced
          vendor_pos[]
          invoices[]   ← vendor invoices
    """
    try:
        # Load all client POs and group by client name
        all_client_pos = db.query(ClientPO).order_by(ClientPO.client_name).all()

        clients_map: dict = {}
        for cpo in all_client_pos:
            clients_map.setdefault(cpo.client_name, []).append(cpo)

        clients_result = []
        for client_name, cpos in clients_map.items():
            client_po_ids = [cpo.id for cpo in cpos]

            # Client invoices linked to any of this client's POs
            client_invoices = (
                db.query(ClientInvoice)
                .filter(ClientInvoice.client_po_id.in_(client_po_ids))
                .all()
            )

            # Vendor POs linked to any of this client's POs
            vendor_pos = (
                db.query(VendorPO)
                .filter(VendorPO.client_po_id.in_(client_po_ids))
                .all()
            )

            # Group vendor POs by vendor name
            vendors_map: dict = {}
            for vpo in vendor_pos:
                vendors_map.setdefault(vpo.vendor_name, []).append(vpo)

            vendors_result = []
            for vendor_name, vpos in vendors_map.items():
                vpo_ids = [vpo.id for vpo in vpos]
                invoices = (
                    db.query(VendorInvoice)
                    .filter(VendorInvoice.vendor_po_id.in_(vpo_ids))
                    .all()
                )
                vendors_result.append(VendorWithInvoices(
                    vendor_name=vendor_name,
                    vendor_pos=[VendorPOResponse.model_validate(v) for v in vpos],
                    total_allocated=sum(v.allocated_value for v in vpos),
                    total_invoiced=sum(i.invoice_amount for i in invoices),
                    invoices=[VendorInvoiceResponse.model_validate(i) for i in invoices],
                ))

            clients_result.append(ClientWithVendors(
                client_name=client_name,
                total_po_value=sum(cpo.total_value for cpo in cpos),
                total_client_invoiced=sum(i.invoice_amount for i in client_invoices),
                client_pos=[ClientPOResponse.model_validate(c) for c in cpos],
                client_invoices=[ClientInvoiceResponse.model_validate(i) for i in client_invoices],
                vendors=vendors_result,
            ))

        return ClientsOverviewResponse(
            clients=clients_result,
            total_clients=len(clients_result),
        )
    except Exception as e:
        import traceback
        print(f"❌ clients-overview error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# REPORTS
# ---------------------------------------------------------------------------

@router.get("/billing-violations", response_model=BillingViolationsResponse)
async def get_billing_violations(db: Session = Depends(get_db)):
    """All overbilled Vendor POs and over-allocated Client POs."""
    try:
        return BillingValidationService(db).get_all_violations()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/margin-summary", response_model=GlobalMarginSummary)
async def get_margin_summary(db: Session = Depends(get_db)):
    """Global margin overview across all Client POs."""
    try:
        return MarginService(db).get_all_margins()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lineage/{document_id}", response_model=Optional[ClientPOLineage])
async def get_lineage_by_document(document_id: str, db: Session = Depends(get_db)):
    """
    Trace the financial lineage from any document_id back to the root Client PO.
    Works for ClientPO, VendorPO, VendorInvoice document IDs.
    """
    try:
        lineage = MarginService(db).get_lineage_by_document(document_id)
        if not lineage:
            raise HTTPException(
                status_code=404,
                detail=f"No financial lineage found for document {document_id}",
            )
        return lineage
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
