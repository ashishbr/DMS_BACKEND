"""
Alert Generation Service
Generates alerts for:
1. PO close to being fully consumed (>80% utilization)
2. Invoice doesn't match its linked PO (amount mismatch, PO not found)
3. Contract/Service Agreement close to expiration (<30 days)
4. Documents outside contract validity period
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.models import Document, Alert
from app.services.document_linking_service import DocumentLinkingService
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
import uuid


class AlertGenerator:
    """Service for generating alerts based on document relationships and status"""
    
    # Alert thresholds
    PO_UTILIZATION_WARNING_THRESHOLD = 0.80  # 80% utilization triggers warning
    PO_UTILIZATION_CRITICAL_THRESHOLD = 0.95  # 95% utilization triggers critical
    CONTRACT_EXPIRY_WARNING_DAYS = 30  # Alert 30 days before expiration
    
    def __init__(self, db: Session):
        self.db = db
        self.linking_service = DocumentLinkingService(db)
    
    def generate_alerts_for_document(self, document: Document) -> List[Alert]:
        """
        Generate alerts for a newly processed document.
        Returns a list of created alerts.
        """
        alerts = []
        
        # Generate alerts based on document type
        if document.category in ["Client Invoice", "Vendor Invoice"]:
            # Link invoice to PO using enhanced linking service
            linked_po = self.linking_service.link_invoice_to_po(document)
            if linked_po:
                document.linked_to = linked_po.id
                self.db.commit()
            
            # Check invoice-PO matching and validation
            invoice_alerts = self._check_invoice_po_match(document, linked_po)
            alerts.extend(invoice_alerts)
            
            # Check PO utilization if invoice is linked to a PO
            if linked_po:
                utilization_alerts = self._check_po_utilization(linked_po.id)
                alerts.extend(utilization_alerts)
                
                # Check contract validity for linked PO
                contract_alerts = self._check_contract_validity_for_po(linked_po)
                alerts.extend(contract_alerts)
        
        elif document.category in ["Client PO", "Vendor PO"]:
            # Link PO to contract
            linked_contract = self.linking_service.link_po_to_contract(document)
            if linked_contract:
                if not document.linked_to:  # Only set if not already linked
                    document.linked_to = linked_contract.id
                    self.db.commit()
            
            # Check PO utilization for this PO
            utilization_alerts = self._check_po_utilization(document.id)
            alerts.extend(utilization_alerts)
            
            # Check contract validity
            if linked_contract:
                contract_alerts = self._check_contract_validity_for_po(document)
                alerts.extend(contract_alerts)
        
        elif document.category in ["Service Agreement"]:
            # Link contract to related POs
            linked_pos = self.linking_service.link_contract_to_po(document)
            
            # Check contract expiration
            expiry_alerts = self._check_contract_expiration(document)
            alerts.extend(expiry_alerts)
            
            # Check if linked POs/invoices are within contract period
            for po in linked_pos:
                validity_alerts = self._check_contract_validity_for_po(po, document)
                alerts.extend(validity_alerts)
        
        return alerts
    
    def _check_contract_validity_for_po(self, po: Document, contract: Document = None) -> List[Alert]:
        """
        Check if a PO and its linked invoices fall within contract validity period.
        Returns alerts if documents are outside contract period.
        """
        alerts = []
        
        # Get contract (either provided or linked to PO)
        if not contract:
            contract = self.linking_service.link_po_to_contract(po)
        
        if not contract or not contract.due_date:
            return alerts
        
        # Check PO validity
        validity = self.linking_service.check_contract_validity_for_document(po, contract)
        if not validity.get("valid"):
            alert = Alert(
                id=str(uuid.uuid4()),
                title="Purchase Order Outside Contract Period",
                description=f"PO {po.title} ({po.created_at.date()}) is outside the validity period of contract {contract.title} (valid until {contract.due_date.date()}). {validity.get('reason', '')}",
                level="warning",
                document_id=po.id,
                timestamp=datetime.utcnow(),
                acknowledged=False
            )
            self.db.add(alert)
            alerts.append(alert)
        
        # Check linked invoices validity
        linked_invoices = self.linking_service.get_linked_invoices(po)
        for invoice in linked_invoices:
            invoice_validity = self.linking_service.check_contract_validity_for_document(invoice, contract)
            if not invoice_validity.get("valid"):
                alert = Alert(
                    id=str(uuid.uuid4()),
                    title="Invoice Outside Contract Period",
                    description=f"Invoice {invoice.title} ({invoice.created_at.date()}) is outside the validity period of contract {contract.title} (valid until {contract.due_date.date()}). {invoice_validity.get('reason', '')}",
                    level="warning",
                    document_id=invoice.id,
                    timestamp=datetime.utcnow(),
                    acknowledged=False
                )
                self.db.add(alert)
                alerts.append(alert)
        
        return alerts
    
    def _check_invoice_po_match(self, invoice: Document, linked_po: Optional[Document] = None) -> List[Alert]:
        """
        Check if an invoice matches its linked PO using enhanced validation.
        Generates alerts for:
        - Invoice amount exceeds PO remaining balance
        - PO not found for invoice
        - Amount mismatch (warning if close, critical if exceeds)
        - Vendor/client mismatches
        - Date anomalies
        """
        alerts = []
        
        # Use provided linked_po or get from invoice.linked_to
        if not linked_po and invoice.linked_to:
            linked_po = self.db.query(Document).filter(Document.id == invoice.linked_to).first()
        
        if not linked_po:
            # Invoice has no linked PO - create warning alert
            alert = Alert(
                id=str(uuid.uuid4()),
                title="Invoice Not Linked to Purchase Order",
                description=f"Invoice {invoice.title} ({invoice.amount:,.2f} {invoice.currency}) could not be matched to a Purchase Order. Please review and link manually.",
                level="warning",
                document_id=invoice.id,
                timestamp=datetime.utcnow(),
                acknowledged=False
            )
            self.db.add(alert)
            alerts.append(alert)
            return alerts
        
        # Use enhanced validation service
        validation = self.linking_service.validate_invoice_against_po(invoice, linked_po)
        
        # Process critical issues
        for issue in validation.get("issues", []):
            alert = Alert(
                id=str(uuid.uuid4()),
                title=issue["type"].replace("_", " ").title(),
                description=f"Invoice {invoice.title}: {issue['message']}. PO: {linked_po.title} (Total: {linked_po.amount:,.2f} {linked_po.currency}).",
                level="critical",
                document_id=invoice.id,
                timestamp=datetime.utcnow(),
                acknowledged=False
            )
            self.db.add(alert)
            alerts.append(alert)
        
        # Process warnings
        for warning in validation.get("warnings", []):
            alert = Alert(
                id=str(uuid.uuid4()),
                title=warning["type"].replace("_", " ").title(),
                description=f"Invoice {invoice.title}: {warning['message']}. PO: {linked_po.title}.",
                level="warning",
                document_id=invoice.id,
                timestamp=datetime.utcnow(),
                acknowledged=False
            )
            self.db.add(alert)
            alerts.append(alert)
        
        return alerts
    
    def _check_po_utilization(self, po_id: str) -> List[Alert]:
        """
        Check if a PO is close to being fully consumed using enhanced consumption calculation.
        Generates alerts when utilization exceeds thresholds.
        """
        alerts = []
        
        po = self.db.query(Document).filter(Document.id == po_id).first()
        if not po or po.category not in ["Client PO", "Vendor PO"]:
            return alerts
        
        # Use enhanced consumption calculation
        consumption = self.linking_service.calculate_po_consumption(po)
        utilization_ratio = consumption["utilization_percentage"] / 100
        remaining_balance = consumption["remaining_balance"]
        total_invoiced = consumption["total_invoiced"]
        linked_invoice_count = consumption["linked_invoice_count"]
        
        # Check thresholds
        if utilization_ratio >= self.PO_UTILIZATION_CRITICAL_THRESHOLD:
            # Critical: PO is almost fully consumed
            alert = Alert(
                id=str(uuid.uuid4()),
                title="Purchase Order Nearly Fully Consumed",
                description=f"PO {po.title} is {consumption['utilization_percentage']:.1f}% utilized ({linked_invoice_count} invoices totaling {total_invoiced:,.2f} {po.currency} of {po.amount:,.2f} {po.currency}). Only {remaining_balance:,.2f} {po.currency} remaining.",
                level="critical",
                document_id=po_id,
                timestamp=datetime.utcnow(),
                acknowledged=False
            )
            self.db.add(alert)
            alerts.append(alert)
        elif utilization_ratio >= self.PO_UTILIZATION_WARNING_THRESHOLD:
            # Warning: PO is getting close to fully consumed
            alert = Alert(
                id=str(uuid.uuid4()),
                title="Purchase Order Approaching Full Utilization",
                description=f"PO {po.title} is {consumption['utilization_percentage']:.1f}% utilized ({linked_invoice_count} invoices totaling {total_invoiced:,.2f} {po.currency} of {po.amount:,.2f} {po.currency}). {remaining_balance:,.2f} {po.currency} remaining.",
                level="warning",
                document_id=po_id,
                timestamp=datetime.utcnow(),
                acknowledged=False
            )
            self.db.add(alert)
            alerts.append(alert)
        
        return alerts
    
    def _check_contract_expiration(self, contract: Document) -> List[Alert]:
        """
        Check if a contract/service agreement is close to expiration.
        Also checks if linked POs/invoices will be affected.
        Generates alerts when expiration is within warning period.
        """
        alerts = []
        
        if not contract.due_date:
            return alerts
        
        # Calculate days until expiration
        days_until_expiry = (contract.due_date - datetime.utcnow()).days
        
        # Get linked POs to include in alert context
        linked_pos = self.linking_service.get_linked_pos_for_contract(contract)
        linked_po_count = len(linked_pos)
        
        # Calculate total PO value and invoice count
        total_po_value = sum(po.amount for po in linked_pos)
        total_invoice_count = 0
        for po in linked_pos:
            invoices = self.linking_service.get_linked_invoices(po)
            total_invoice_count += len(invoices)
        
        if days_until_expiry < 0:
            # Contract has expired
            context = ""
            if linked_po_count > 0:
                context = f" This contract governs {linked_po_count} PO(s) worth {total_po_value:,.2f} {contract.currency} with {total_invoice_count} linked invoice(s)."
            
            alert = Alert(
                id=str(uuid.uuid4()),
                title="Contract Has Expired",
                description=f"Service Agreement {contract.title} expired on {contract.due_date.strftime('%Y-%m-%d')}.{context} Please renew or terminate.",
                level="critical",
                document_id=contract.id,
                timestamp=datetime.utcnow(),
                acknowledged=False
            )
            self.db.add(alert)
            alerts.append(alert)
        elif days_until_expiry <= self.CONTRACT_EXPIRY_WARNING_DAYS:
            # Contract is expiring soon
            context = ""
            if linked_po_count > 0:
                context = f" This contract governs {linked_po_count} PO(s) worth {total_po_value:,.2f} {contract.currency} with {total_invoice_count} linked invoice(s)."
            
            alert = Alert(
                id=str(uuid.uuid4()),
                title="Contract Expiring Soon",
                description=f"Service Agreement {contract.title} will expire in {days_until_expiry} days ({contract.due_date.strftime('%Y-%m-%d')}).{context} Please review renewal options.",
                level="warning",
                document_id=contract.id,
                timestamp=datetime.utcnow(),
                acknowledged=False
            )
            self.db.add(alert)
            alerts.append(alert)
        
        return alerts
    
    def refresh_all_alerts(self) -> int:
        """
        Refresh alerts for all documents.
        Useful for periodic updates or after bulk imports.
        Returns the number of alerts generated.
        """
        # Delete existing unacknowledged alerts
        self.db.query(Alert).filter(Alert.acknowledged == False).delete()
        
        # Get all documents
        documents = self.db.query(Document).all()
        
        total_alerts = 0
        for document in documents:
            alerts = self.generate_alerts_for_document(document)
            total_alerts += len(alerts)
        
        self.db.commit()
        return total_alerts

