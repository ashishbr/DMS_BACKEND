from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from typing import List
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.upload_service import UploadService
from app.schemas import UploadResponse
import os

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

@router.post("/", response_model=UploadResponse)
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload multiple files"""
    try:
        upload_service = UploadService()
        response = await upload_service.upload_files(files)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload files: {str(e)}")

@router.get("/{filename}")
async def get_file(filename: str):
    """Get an uploaded file"""
    try:
        upload_service = UploadService()
        file_path = upload_service.get_file_path(filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(file_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file: {str(e)}")

@router.delete("/{filename}")
async def delete_file(filename: str):
    """Delete an uploaded file"""
    try:
        upload_service = UploadService()
        success = upload_service.delete_file(filename)
        
        if not success:
            raise HTTPException(status_code=404, detail="File not found")
        
        return {"message": "File deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@router.post("/sync-cache-to-db")
async def sync_cache_to_db(db: Session = Depends(get_db)):
    """
    One-shot repair: scan all processed JSON cache files and insert any documents
    that are missing from the documents table.  Safe to call multiple times.

    This fixes cases where the JSON cache was written but the DB insert was skipped
    due to a false-positive deduplication match (e.g. Vendor Invoice matched against
    Client PO with the same po_number).
    """
    import json, os
    from app.services.upload_service import UploadService
    from app.services.pdf_processor import PDFProcessor
    from app.models import Document

    upload_svc = UploadService()
    processed_dir = PDFProcessor().processed_dir

    inserted = 0
    skipped = 0
    errors = []

    if not os.path.exists(processed_dir):
        return {"inserted": 0, "skipped": 0, "errors": [], "message": "No cache directory found."}

    for fname in os.listdir(processed_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(processed_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not data.get("success"):
                skipped += 1
                continue

            doc_id = data.get("document_id")
            if not doc_id:
                skipped += 1
                continue

            # Check if already in DB by document_id
            existing = db.query(Document).filter(Document.id == doc_id).first()
            if existing:
                skipped += 1
                continue

            # Not in DB — insert it now using the fixed dedup logic
            ex = data.get("extracted_data", {})
            doc_type = data.get("document_type")

            # Prefer source_filename embedded at save time; fall back to
            # scanning the uploads directory for a matching file.
            source_filename = data.get("source_filename")
            if not source_filename:
                upload_dir = upload_svc.upload_dir
                if os.path.exists(upload_dir):
                    stem = doc_id.lower()
                    for uf in os.listdir(upload_dir):
                        if uf.lower().endswith(".pdf") and (stem in uf.lower() or uf.lower().replace(".pdf", "") in stem):
                            source_filename = uf
                            break
                source_filename = source_filename or f"{doc_id}.pdf"  # best-effort fallback

            # Double-check with category-aware dedup before inserting
            dup = upload_svc._check_document_exists_in_db(source_filename, db, ex, doc_type)
            if dup:
                skipped += 1
                continue

            doc = upload_svc._save_to_database(data, source_filename, db)
            if doc:
                try:
                    from app.services.financial_classification_service import FinancialClassificationService
                    FinancialClassificationService(db).classify_and_create(doc, ex)
                    db.commit()
                    inserted += 1
                except Exception as fin_err:
                    db.rollback()
                    # Document row already committed in _save_to_database; only financial record lost
                    inserted += 1
                    errors.append(f"{doc_id}: financial classification failed — {fin_err}")

        except Exception as e:
            errors.append(f"{fname}: {e}")
            db.rollback()

    return {
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "message": f"Inserted {inserted} missing document(s) into the DB.",
    }


@router.post("/process/{filename}")
async def process_pdf(filename: str, db: Session = Depends(get_db)):
    """Process an uploaded PDF file and extract data"""
    try:
        upload_service = UploadService()
        result = await upload_service.process_uploaded_pdf(filename, db)
        
        if not result.get("success", False):
            error_message = result.get("error", "Processing failed")
            # Log the error for debugging
            print(f"❌ Processing failed for {filename}: {error_message}")
            raise HTTPException(
                status_code=400, 
                detail=error_message,
                headers={"X-Error-Type": result.get("error_type", "processing_error")}
            )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to process PDF: {str(e)}"
        print(f"❌ Exception processing {filename}: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)
