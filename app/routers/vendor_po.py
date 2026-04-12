"""
Vendor PO Router  (/api/vendor-po)
-----------------------------------
Endpoints for the standalone Vendor PO Generator.

  POST  /api/vendor-po/generate   — create PO + generate PDF  (primary)
  POST  /api/vendor-po            — alias for /generate
  GET   /api/vendor-po            — list all generated POs
  GET   /api/vendor-po/{po_id}    — get single PO by ID
  PUT   /api/vendor-po/{po_id}    — partial update + re-generate PDF
  DELETE /api/vendor-po/{po_id}   — delete PO (and its PDF)

  POST  /api/vendor-po/{po_id}/regenerate-pdf  — force regenerate PDF
"""
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    GeneratedVendorPOCreate,
    GeneratedVendorPOResponse,
    GeneratedVendorPOUpdate,
)
from app.services.vendor_po_service import VendorPOService

router = APIRouter(prefix="/api/vendor-po", tags=["vendor-po"])


# ---------------------------------------------------------------------------
# Create — registered on two paths explicitly (stacking decorators is unreliable)
# ---------------------------------------------------------------------------

async def _create_vendor_po(payload: GeneratedVendorPOCreate, db: Session = Depends(get_db)):
    try:
        svc = VendorPOService(db)
        if payload.po_number and svc.get_by_po_number(payload.po_number):
            raise HTTPException(
                status_code=409,
                detail=f"PO number '{payload.po_number}' already exists.",
            )
        return svc.create(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/generate", response_model=GeneratedVendorPOResponse, status_code=201)
async def create_vendor_po_generate(
    payload: GeneratedVendorPOCreate, db: Session = Depends(get_db)
):
    """Create a Vendor PO + generate PDF.  Primary endpoint used by the frontend."""
    return await _create_vendor_po(payload, db)


@router.post("", response_model=GeneratedVendorPOResponse, status_code=201)
async def create_vendor_po_root(
    payload: GeneratedVendorPOCreate, db: Session = Depends(get_db)
):
    """Alias — same as /generate."""
    return await _create_vendor_po(payload, db)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("", response_model=List[GeneratedVendorPOResponse])
async def list_vendor_pos(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
    client_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Return generated Vendor POs, most recent first. Filter by client_name if provided."""
    try:
        return VendorPOService(db).list_all(skip=skip, limit=limit, client_name=client_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Get single
# ---------------------------------------------------------------------------

@router.get("/{po_id}", response_model=GeneratedVendorPOResponse)
async def get_vendor_po(po_id: str, db: Session = Depends(get_db)):
    po = VendorPOService(db).get(po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Vendor PO not found.")
    return po


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@router.put("/{po_id}", response_model=GeneratedVendorPOResponse)
async def update_vendor_po(
    po_id: str,
    payload: GeneratedVendorPOUpdate,
    db: Session = Depends(get_db),
):
    """
    Partially update a Vendor PO.

    - If ``line_items`` are supplied, the existing items are **replaced** entirely.
    - The PDF is regenerated automatically after any change.
    """
    try:
        updated = VendorPOService(db).update(po_id, payload)
        if not updated:
            raise HTTPException(status_code=404, detail="Vendor PO not found.")
        return updated
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/{po_id}", status_code=200)
async def delete_vendor_po(po_id: str, db: Session = Depends(get_db)):
    deleted = VendorPOService(db).delete(po_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Vendor PO not found.")
    return {"success": True, "id": po_id}


# ---------------------------------------------------------------------------
# Download PDF
# ---------------------------------------------------------------------------

@router.get("/{po_id}/pdf")
async def download_vendor_po_pdf(po_id: str, db: Session = Depends(get_db)):
    """Stream the generated PDF for a Vendor PO."""
    po = VendorPOService(db).get(po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Vendor PO not found.")
    if not po.pdf_path or not os.path.exists(po.pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found. Try regenerating it.")
    return FileResponse(
        po.pdf_path,
        media_type="application/pdf",
        filename=f"{po.po_number}.pdf",
    )


# ---------------------------------------------------------------------------
# Status transition
# ---------------------------------------------------------------------------

@router.patch("/{po_id}/status", response_model=GeneratedVendorPOResponse)
async def advance_status(
    po_id: str,
    body: dict,
    db: Session = Depends(get_db),
):
    """
    Advance a Vendor PO's status.

    Body: ``{"status": "SENT"}``

    Allowed transitions:
      DRAFT → SENT
      SENT  → APPROVED | DRAFT
      APPROVED → ACTIVE | CLOSED
      ACTIVE → CLOSED
    """
    new_status = body.get("status")
    if not new_status:
        raise HTTPException(status_code=422, detail="'status' field required in body.")
    try:
        updated = VendorPOService(db).advance_status(po_id, new_status.upper())
        if updated is None:
            raise HTTPException(status_code=404, detail="Vendor PO not found.")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Force-regenerate PDF
# ---------------------------------------------------------------------------

@router.post("/{po_id}/regenerate-pdf", response_model=GeneratedVendorPOResponse)
async def regenerate_pdf(po_id: str, db: Session = Depends(get_db)):
    """Force-regenerate the PDF for an existing Vendor PO."""
    svc = VendorPOService(db)
    pdf_path = svc.regenerate_pdf(po_id)
    if pdf_path is None:
        raise HTTPException(status_code=404, detail="Vendor PO not found.")
    po = svc.get(po_id)
    return po
