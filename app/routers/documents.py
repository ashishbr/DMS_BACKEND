from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.services.document_service import DocumentService
from app.services.exception_service import ExceptionService
from app.services.alert_service import AlertService
from app.schemas import (
    Document, DocumentCreate, DocumentUpdate, DocumentDetailResponse, MSABucketResponse,
    DocumentLinkRequest, DocumentCategoryUpdate, DocumentClientLinkRecord,
)
# Thin helper so we can call update_document with partial data without
# polluting the lambda trick
def _partial_update(**fields) -> DocumentUpdate:
    return DocumentUpdate(**fields)
from typing import Dict, Any
import uuid

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.get("/", response_model=Dict[str, List[Document]])
async def get_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Get list of documents with pagination"""
    try:
        document_service = DocumentService(db)
        documents = document_service.get_documents(skip=skip, limit=limit)
        return {"documents": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch documents: {str(e)}")

@router.get("/msa-buckets", response_model=MSABucketResponse)
async def get_msa_buckets(
    db: Session = Depends(get_db)
):
    """Group documents by MSA number, including linked POs and invoices"""
    try:
        document_service = DocumentService(db)
        return document_service.get_msa_buckets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch MSA buckets: {str(e)}")

@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    document_id: str,
    db: Session = Depends(get_db)
):
    """Get document details with related exceptions and alerts"""
    try:
        document_service = DocumentService(db)
        exception_service = ExceptionService(db)
        alert_service = AlertService(db)
        
        document = document_service.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        related_exceptions = exception_service.get_exceptions_by_document(document_id)
        related_alerts = alert_service.get_alerts_by_document(document_id)
        
        return DocumentDetailResponse(
            document=document,
            related_exceptions=related_exceptions,
            related_alerts=related_alerts
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch document details: {str(e)}")

@router.post("/", response_model=Document)
async def create_document(
    document: DocumentCreate,
    db: Session = Depends(get_db)
):
    """Create a new document"""
    try:
        document_service = DocumentService(db)
        return document_service.create_document(document)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create document: {str(e)}")

@router.put("/{document_id}", response_model=Document)
async def update_document(
    document_id: str,
    document: DocumentUpdate,
    db: Session = Depends(get_db)
):
    """Update a document"""
    try:
        document_service = DocumentService(db)
        updated_document = document_service.update_document(document_id, document)
        if not updated_document:
            raise HTTPException(status_code=404, detail="Document not found")
        return updated_document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update document: {str(e)}")

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    db: Session = Depends(get_db)
):
    """Delete a document"""
    try:
        document_service = DocumentService(db)
        success = document_service.delete_document(document_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"message": "Document deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


# ---------------------------------------------------------------------------
# Document → Client linking  (manual UI assignments)
# ---------------------------------------------------------------------------

@router.post("/{document_id}/link", response_model=Document)
async def link_document_to_client(
    document_id: str,
    payload: DocumentLinkRequest,
    db: Session = Depends(get_db),
):
    """
    Manually assign a document to a client.
    Records the action in document_client_links, updates doc.client, cascades
    to financial tables (ClientPO / ClientInvoice), then runs relink.
    """
    from datetime import datetime
    from app.models import DocumentClientLink
    from app.services.relink_service import RelinkService

    document_service = DocumentService(db)
    doc = document_service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    client_name = payload.client_name.strip()
    if not client_name:
        raise HTTPException(status_code=422, detail="client_name cannot be empty")

    try:
        # Deactivate any previous active link for this document
        existing = (
            db.query(DocumentClientLink)
            .filter(
                DocumentClientLink.document_id == document_id,
                DocumentClientLink.is_active == True,
            )
            .all()
        )
        for link in existing:
            link.is_active = False
            link.unlinked_at = datetime.utcnow()

        # Record the new link
        new_link = DocumentClientLink(
            id=str(uuid.uuid4()),
            document_id=document_id,
            client_name=client_name,
            is_active=True,
            linked_by=payload.linked_by,
        )
        db.add(new_link)
        db.flush()

        # Update doc.client and cascade to financial tables
        updated = document_service.update_document(
            document_id, _partial_update(client=client_name)
        )

        # Run relink so financial layers stay in sync
        try:
            RelinkService(db).run_full_relink()
        except Exception as relink_err:
            print(f"[link] relink warning: {relink_err}")

        db.commit()
        db.refresh(updated)
        return updated

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to link document: {str(e)}")


@router.delete("/{document_id}/link", response_model=Document)
async def unlink_document_from_client(
    document_id: str,
    db: Session = Depends(get_db),
):
    """
    Remove the manual client assignment for a document.
    Marks the link record inactive, clears doc.client to 'Unknown Client'.
    Does NOT delete financial records — just severs the client association.
    """
    from datetime import datetime
    from app.models import DocumentClientLink
    from app.services.relink_service import RelinkService

    document_service = DocumentService(db)
    doc = document_service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        # Mark existing active links as inactive
        active_links = (
            db.query(DocumentClientLink)
            .filter(
                DocumentClientLink.document_id == document_id,
                DocumentClientLink.is_active == True,
            )
            .all()
        )
        for link in active_links:
            link.is_active = False
            link.unlinked_at = datetime.utcnow()
        db.flush()

        # Clear doc.client
        updated = document_service.update_document(
            document_id, _partial_update(client="Unknown Client")
        )

        try:
            RelinkService(db).run_full_relink()
        except Exception as relink_err:
            print(f"[unlink] relink warning: {relink_err}")

        db.commit()
        db.refresh(updated)
        return updated

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to unlink document: {str(e)}")


@router.patch("/{document_id}/category", response_model=Document)
async def update_document_category(
    document_id: str,
    payload: DocumentCategoryUpdate,
    db: Session = Depends(get_db),
):
    """Update only the category of a document."""
    from app.services.relink_service import RelinkService

    document_service = DocumentService(db)
    doc = document_service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    category = payload.category.strip()
    if not category:
        raise HTTPException(status_code=422, detail="category cannot be empty")

    try:
        updated = document_service.update_document(
            document_id, _partial_update(category=category)
        )
        try:
            RelinkService(db).run_full_relink()
        except Exception as relink_err:
            print(f"[category] relink warning: {relink_err}")

        db.commit()
        db.refresh(updated)
        return updated
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update category: {str(e)}")


@router.patch("/{document_id}/fields", response_model=Document)
async def update_document_fields(
    document_id: str,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
):
    """
    Correct extracted fields post-processing (fix OCR errors, fill missing
    PO / invoice numbers, etc.).  Cascades changes to the corresponding
    financial record (ClientPO, VendorPO, ClientInvoice, or VendorInvoice),
    re-runs document linking, and patches the JSON cache file so the
    Document Inventory view reflects the corrections immediately.
    """
    from app.services.relink_service import RelinkService
    from app.services.pdf_processor import PDFProcessor

    document_service = DocumentService(db)
    updated = document_service.update_document_fields(document_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")

    # Patch the JSON cache file so the processed-documents viewer reflects
    # the corrections without needing to re-process the PDF.
    fields_changed = payload.model_dump(mode="json", exclude_unset=True)
    if fields_changed:
        try:
            PDFProcessor().update_cache_fields(document_id, fields_changed)
        except Exception as cache_err:
            print(f"[fields] cache update warning: {cache_err}")

    try:
        RelinkService(db).run_full_relink()
    except Exception as relink_err:
        print(f"[fields] relink warning: {relink_err}")

    db.commit()
    db.refresh(updated)
    return updated


@router.get("/{document_id}/link-history", response_model=List[DocumentClientLinkRecord])
async def get_link_history(
    document_id: str,
    db: Session = Depends(get_db),
):
    """Return the full link/unlink audit trail for a document."""
    from app.models import DocumentClientLink

    doc = DocumentService(db).get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    links = (
        db.query(DocumentClientLink)
        .filter(DocumentClientLink.document_id == document_id)
        .order_by(DocumentClientLink.linked_at.desc())
        .all()
    )
    return links
