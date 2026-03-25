"""
Enhanced Document Linking Service
Provides sophisticated linking between:
- Invoices → Purchase Orders
- Contracts/Service Agreements → Purchase Orders
- Supports multiple linking strategies for better accuracy
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.models import Document
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
import re


class DocumentLinkingService:
    """Service for linking related documents with multiple strategies"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def link_invoice_to_po(self, invoice: Document) -> Optional[Document]:
        """
        Link an invoice to a Purchase Order using multiple strategies.
        Returns the linked PO document, or None if no match found.
        
        Strategies (in priority order):
        1. Exact PO number match (from invoice.po_number)
        2. PO number in invoice title or extracted data
        3. Client + Vendor match with date proximity
        4. Client match with amount similarity
        """
        if invoice.category not in ["Client Invoice", "Vendor Invoice"]:
            return None
        
        # Strategy 1: Exact PO number match (highest priority)
        if invoice.po_number:
            po = self._find_po_by_po_number(invoice.po_number)
            if po:
                return po
        
        # Strategy 2: Extract PO number from invoice title/description
        po_number_from_title = self._extract_po_number_from_text(invoice.title)
        if po_number_from_title:
            po = self._find_po_by_po_number(po_number_from_title)
            if po:
                return po
        
        # Strategy 3: Client + Vendor match with date proximity (within 1 year)
        if invoice.vendor:
            po = self._find_po_by_client_vendor_date(
                invoice.client, 
                invoice.vendor, 
                invoice.created_at
            )
            if po:
                return po
        
        # Strategy 4: Client match with amount similarity (within 20% difference)
        po = self._find_po_by_client_amount(
            invoice.client,
            invoice.amount,
            invoice.currency
        )
        if po:
            return po
        
        return None
    
    def link_contract_to_po(self, contract: Document) -> List[Document]:
        """
        Link a contract/service agreement to related Purchase Orders.
        Returns a list of linked PO documents.
        
        Strategies:
        1. Vendor + Client match
        2. Date range overlap (PO created within contract validity period)
        3. Amount similarity
        """
        if contract.category != "Service Agreement":
            return []
        
        linked_pos = []
        
        # Strategy 1: Vendor + Client match with date range
        if contract.vendor and contract.due_date:
            pos = self._find_pos_by_vendor_client_date_range(
                contract.vendor,
                contract.client,
                contract.created_at,
                contract.due_date
            )
            linked_pos.extend(pos)
        
        # Strategy 2: Client match with date range
        if contract.due_date:
            pos = self._find_pos_by_client_date_range(
                contract.client,
                contract.created_at,
                contract.due_date
            )
            # Avoid duplicates
            existing_ids = {po.id for po in linked_pos}
            for po in pos:
                if po.id not in existing_ids:
                    linked_pos.append(po)
        
        return linked_pos
    
    def link_po_to_contract(self, po: Document) -> Optional[Document]:
        """
        Link a Purchase Order to its governing contract/service agreement.
        Returns the linked contract document, or None if no match found.
        """
        if po.category not in ["Client PO", "Vendor PO"]:
            return None
        
        # Strategy 1: Vendor + Client match with date range
        if po.vendor:
            contract = self._find_contract_by_vendor_client_date(
                po.vendor,
                po.client,
                po.created_at
            )
            if contract:
                return contract
        
        # Strategy 2: Client match with date range
        contract = self._find_contract_by_client_date(
            po.client,
            po.created_at
        )
        if contract:
            return contract
        
        return None
    
    def get_linked_invoices(self, po: Document) -> List[Document]:
        """Get all invoices linked to a specific PO"""
        return self.db.query(Document).filter(
            Document.linked_to == po.id,
            Document.category.in_(["Client Invoice", "Vendor Invoice"])
        ).all()
    
    def get_linked_pos_for_contract(self, contract: Document) -> List[Document]:
        """Get all POs linked to a specific contract"""
        # Find POs that reference this contract or match vendor/client
        pos = []
        
        # Direct link (if PO has linked_to pointing to contract)
        direct_pos = self.db.query(Document).filter(
            Document.linked_to == contract.id,
            Document.category.in_(["Client PO", "Vendor PO"])
        ).all()
        pos.extend(direct_pos)
        
        # Indirect link (vendor/client match within contract period)
        if contract.vendor and contract.due_date:
            indirect_pos = self._find_pos_by_vendor_client_date_range(
                contract.vendor,
                contract.client,
                contract.created_at,
                contract.due_date
            )
            # Avoid duplicates
            existing_ids = {p.id for p in pos}
            for p in indirect_pos:
                if p.id not in existing_ids:
                    pos.append(p)
        
        return pos
    
    def calculate_po_consumption(self, po: Document) -> Dict[str, float]:
        """
        Calculate PO consumption by summing all linked invoices.
        Returns a dict with:
        - total_invoiced: Sum of all linked invoice amounts
        - remaining_balance: PO amount - total_invoiced
        - utilization_percentage: (total_invoiced / po.amount) * 100
        """
        linked_invoices = self.get_linked_invoices(po)
        
        # Sum invoice amounts (handle currency conversion if needed)
        total_invoiced = 0.0
        for invoice in linked_invoices:
            # For now, assume same currency (could add currency conversion later)
            if invoice.currency == po.currency:
                total_invoiced += invoice.amount
            else:
                # Different currency - add anyway but could flag this
                total_invoiced += invoice.amount
        
        remaining_balance = po.amount - total_invoiced
        utilization_percentage = (total_invoiced / po.amount * 100) if po.amount > 0 else 0
        
        return {
            "total_invoiced": total_invoiced,
            "remaining_balance": remaining_balance,
            "utilization_percentage": utilization_percentage,
            "linked_invoice_count": len(linked_invoices)
        }
    
    def validate_invoice_against_po(self, invoice: Document, po: Document) -> Dict[str, Any]:
        """
        Validate an invoice against its linked PO.
        Returns a dict with validation results and issues found.
        """
        issues = []
        warnings = []
        
        # Check amount
        consumption = self.calculate_po_consumption(po)
        if invoice.amount > consumption["remaining_balance"]:
            issues.append({
                "type": "amount_exceeds_balance",
                "message": f"Invoice amount (${invoice.amount:,.2f}) exceeds remaining PO balance (${consumption['remaining_balance']:,.2f})"
            })
        elif invoice.amount > consumption["remaining_balance"] * 0.9:
            warnings.append({
                "type": "amount_close_to_balance",
                "message": f"Invoice amount is close to exceeding remaining PO balance"
            })
        
        # Check currency
        if invoice.currency != po.currency:
            warnings.append({
                "type": "currency_mismatch",
                "message": f"Invoice currency ({invoice.currency}) differs from PO currency ({po.currency})"
            })
        
        # Check vendor (if both have vendor)
        if invoice.vendor and po.vendor:
            if invoice.vendor.lower() != po.vendor.lower():
                warnings.append({
                    "type": "vendor_mismatch",
                    "message": f"Invoice vendor ({invoice.vendor}) differs from PO vendor ({po.vendor})"
                })
        
        # Check client
        if invoice.client.lower() != po.client.lower():
            warnings.append({
                "type": "client_mismatch",
                "message": f"Invoice client ({invoice.client}) differs from PO client ({po.client})"
            })
        
        # Check date (invoice should be after PO creation)
        if invoice.created_at < po.created_at:
            warnings.append({
                "type": "date_anomaly",
                "message": f"Invoice date ({invoice.created_at.date()}) is before PO creation date ({po.created_at.date()})"
            })
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "po_balance": consumption["remaining_balance"],
            "po_utilization": consumption["utilization_percentage"]
        }
    
    def check_contract_validity_for_document(self, document: Document, contract: Document) -> Dict[str, Any]:
        """
        Check if a document (PO or invoice) falls within a contract's validity period.
        Returns validation results.
        """
        if not contract.due_date:
            return {
                "valid": False,
                "reason": "Contract has no expiration date"
            }
        
        # Check if document date is within contract period
        contract_start = contract.created_at
        contract_end = contract.due_date
        
        doc_date = document.created_at
        
        if doc_date < contract_start:
            return {
                "valid": False,
                "reason": f"Document date ({doc_date.date()}) is before contract start ({contract_start.date()})"
            }
        
        if doc_date > contract_end:
            return {
                "valid": False,
                "reason": f"Document date ({doc_date.date()}) is after contract expiration ({contract_end.date()})"
            }
        
        # Check days until expiration
        days_until_expiry = (contract_end - datetime.utcnow()).days
        
        return {
            "valid": True,
            "within_period": True,
            "days_until_expiry": days_until_expiry,
            "contract_start": contract_start,
            "contract_end": contract_end
        }
    
    # Private helper methods
    
    def _find_po_by_po_number(self, po_number: str) -> Optional[Document]:
        """Find PO by exact PO number match"""
        # Try exact match in po_number field
        po = self.db.query(Document).filter(
            Document.category.in_(["Client PO", "Vendor PO"]),
            Document.po_number == po_number
        ).first()
        
        if po:
            return po
        
        # Try partial match in title
        po = self.db.query(Document).filter(
            Document.category.in_(["Client PO", "Vendor PO"]),
            Document.title.contains(po_number)
        ).first()
        
        return po
    
    def _extract_po_number_from_text(self, text: str) -> Optional[str]:
        """Extract PO number from text using regex patterns"""
        patterns = [
            r"PO[:\s#-]*([A-Z0-9-]+)",
            r"Purchase\s+Order[:\s#-]*([A-Z0-9-]+)",
            r"P\.O\.\s*[:\s#-]*([A-Z0-9-]+)",
            r"P\/O[:\s#-]*([A-Z0-9-]+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                po_num = match.group(1).strip()
                if len(po_num) > 2:
                    return po_num
        
        return None
    
    def _find_po_by_client_vendor_date(
        self, 
        client: str, 
        vendor: str, 
        invoice_date: datetime,
        days_tolerance: int = 365
    ) -> Optional[Document]:
        """Find PO by client, vendor, and date proximity"""
        date_start = invoice_date - timedelta(days=days_tolerance)
        date_end = invoice_date + timedelta(days=30)  # PO should be before invoice
        
        po = self.db.query(Document).filter(
            Document.category.in_(["Client PO", "Vendor PO"]),
            Document.client == client,
            Document.vendor == vendor,
            Document.created_at >= date_start,
            Document.created_at <= date_end
        ).order_by(Document.created_at.desc()).first()
        
        return po
    
    def _find_po_by_client_amount(
        self,
        client: str,
        amount: float,
        currency: str,
        tolerance_percent: float = 0.2
    ) -> Optional[Document]:
        """Find PO by client and amount similarity"""
        amount_min = amount * (1 - tolerance_percent)
        amount_max = amount * (1 + tolerance_percent)
        
        po = self.db.query(Document).filter(
            Document.category.in_(["Client PO", "Vendor PO"]),
            Document.client == client,
            Document.currency == currency,
            Document.amount >= amount_min,
            Document.amount <= amount_max
        ).order_by(Document.created_at.desc()).first()
        
        return po
    
    def _find_pos_by_vendor_client_date_range(
        self,
        vendor: str,
        client: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Document]:
        """Find POs by vendor, client, and date range"""
        return self.db.query(Document).filter(
            Document.category.in_(["Client PO", "Vendor PO"]),
            Document.vendor == vendor,
            Document.client == client,
            Document.created_at >= start_date,
            Document.created_at <= end_date
        ).all()
    
    def _find_pos_by_client_date_range(
        self,
        client: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Document]:
        """Find POs by client and date range"""
        return self.db.query(Document).filter(
            Document.category.in_(["Client PO", "Vendor PO"]),
            Document.client == client,
            Document.created_at >= start_date,
            Document.created_at <= end_date
        ).all()
    
    def _find_contract_by_vendor_client_date(
        self,
        vendor: str,
        client: str,
        po_date: datetime
    ) -> Optional[Document]:
        """Find contract by vendor, client, and date (PO should be within contract period)"""
        contract = self.db.query(Document).filter(
            Document.category == "Service Agreement",
            Document.vendor == vendor,
            Document.client == client,
            Document.created_at <= po_date,
            or_(
                Document.due_date >= po_date,
                Document.due_date.is_(None)
            )
        ).order_by(Document.created_at.desc()).first()
        
        return contract
    
    def _find_contract_by_client_date(
        self,
        client: str,
        po_date: datetime
    ) -> Optional[Document]:
        """Find contract by client and date"""
        contract = self.db.query(Document).filter(
            Document.category == "Service Agreement",
            Document.client == client,
            Document.created_at <= po_date,
            or_(
                Document.due_date >= po_date,
                Document.due_date.is_(None)
            )
        ).order_by(Document.created_at.desc()).first()
        
        return contract

