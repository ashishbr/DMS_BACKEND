from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict
from app.services.pdf_processor import PDFProcessor
import asyncio
import os
import json

router = APIRouter(prefix="/api/processed-documents", tags=["processed-documents"])


def _read_processed_documents_sync():
    processor = PDFProcessor()
    processed_dir = processor.processed_dir

    if not os.path.exists(processed_dir):
        return {"documents": []}

    documents = []
    seen_document_ids = set()

    for filename in os.listdir(processed_dir):
        if filename.endswith('.json'):
            file_path = os.path.join(processed_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # Skip if not successful
                    if not data.get('success', False):
                        continue

                    # Deduplicate strictly by document_id only —
                    # content-based dedup (title+amount+client) incorrectly
                    # collapses distinct documents that share those values.
                    doc_id = data.get('document_id')
                    if not doc_id or doc_id in seen_document_ids:
                        continue

                    seen_document_ids.add(doc_id)
                    doc_summary = {k: v for k, v in data.items() if k != "full_text"}
                    documents.append(doc_summary)
            except Exception as e:
                print(f"Error reading {filename}: {e}")
                continue

    # Sort by processing time (newest first)
    documents.sort(key=lambda x: x.get('processing_time', ''), reverse=True)

    return {"documents": documents}


@router.get("/")
async def get_processed_documents():
    """Get list of processed documents with their extracted content"""
    try:
        return await asyncio.to_thread(_read_processed_documents_sync)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get processed documents: {str(e)}")

@router.get("/{document_id}")
async def get_processed_document(document_id: str):
    """Get specific processed document by ID"""
    try:
        processor = PDFProcessor()
        processed_dir = processor.processed_dir
        
        # Look for JSON file with this document ID
        for filename in os.listdir(processed_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(processed_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get('document_id') == document_id:
                            return data
                except Exception as e:
                    continue
        
        raise HTTPException(status_code=404, detail="Document not found")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get document: {str(e)}")

@router.get("/content/{document_id}")
async def get_document_content(document_id: str):
    """Get the full text content of a processed document"""
    try:
        processor = PDFProcessor()
        processed_dir = processor.processed_dir
        
        # Look for JSON file with this document ID
        for filename in os.listdir(processed_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(processed_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get('document_id') == document_id:
                            return {
                                "document_id": document_id,
                                "full_text": data.get('full_text', ''),
                                "extracted_data": data.get('extracted_data', {}),
                                "processing_time": data.get('processing_time', '')
                            }
                except Exception as e:
                    continue
        
        raise HTTPException(status_code=404, detail="Document not found")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get document content: {str(e)}")

@router.delete("/{document_id}")
async def delete_processed_document(document_id: str):
    """Delete a processed document by ID"""
    try:
        processor = PDFProcessor()
        processed_dir = processor.processed_dir
        
        # Look for JSON file with this document ID
        for filename in os.listdir(processed_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(processed_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get('document_id') == document_id:
                            # Delete the JSON file
                            os.remove(file_path)
                            return {"message": "Document deleted successfully", "document_id": document_id}
                except Exception as e:
                    continue
        
        raise HTTPException(status_code=404, detail="Document not found")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")
