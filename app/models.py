from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)  # Client PO, Vendor PO, Client Invoice, Vendor Invoice, Service Agreement
    client = Column(String, nullable=False)
    vendor = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    status = Column(String, default="Draft")  # Draft, Approved, Pending Review, Flagged
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    due_date = Column(DateTime(timezone=True), nullable=True)
    confidence = Column(Float, default=0.0)
    linked_to = Column(String, nullable=True)
    pdf_url = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    processed = Column(Boolean, default=False)
    po_number = Column(String, nullable=True, index=True)
    invoice_number = Column(String, nullable=True, index=True)
    msa_number = Column(String, nullable=True, index=True)
    processing_status = Column(String, nullable=True, index=True)
    # UPLOADED | EXTRACTED | CLASSIFIED | PARSED | VALIDATED | FAILED
    extracted_json = Column(Text, nullable=True)  # raw OCR JSON dump


class Exception(Base):
    __tablename__ = "exceptions"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    issue = Column(Text, nullable=False)
    severity = Column(String, nullable=False)  # low, medium, high
    owner = Column(String, nullable=False)
    raised_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved = Column(Boolean, default=False)

    document = relationship("Document", back_populates="exceptions")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    level = Column(String, nullable=False)  # info, warning, critical
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged = Column(Boolean, default=False)
    document_id = Column(String, ForeignKey("documents.id"), nullable=True)

    document = relationship("Document", back_populates="alerts")


Document.exceptions = relationship("Exception", back_populates="document")
Document.alerts = relationship("Alert", back_populates="document")


# ---------------------------------------------------------------------------
# LAYER 1 — Client POs  (Revenue Layer)
# ---------------------------------------------------------------------------

class ClientPO(Base):
    """
    Revenue commitment from a client.
    One ClientPO → many VendorPOs via POAllocation.
    Always originates from an uploaded document.
    """
    __tablename__ = "client_pos"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, unique=True)
    po_number = Column(String, nullable=False, index=True)
    client_name = Column(String, nullable=False, index=True)
    total_value = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    service_scope = Column(Text, nullable=True)
    issue_date = Column(DateTime(timezone=True), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="DRAFT")  # DRAFT | APPROVED | ACTIVE | CLOSED
    msa_number = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", foreign_keys=[document_id])
    allocations = relationship("POAllocation", back_populates="client_po", cascade="all, delete-orphan")
    client_invoices = relationship("ClientInvoice", back_populates="client_po")


# ---------------------------------------------------------------------------
# LAYER 2 — POAllocation  (Internal EMB Mapping)
# ---------------------------------------------------------------------------

class POAllocation(Base):
    """
    Maps one Client PO to one Vendor PO with an allocated amount.
    SUM(allocated_value per client_po_id) is compared to ClientPO.total_value for margin tracking.
    Over-allocation raises a warning (not a hard block).
    Unique constraint prevents double-mapping the same pair.
    """
    __tablename__ = "client_po_vendor_po_mapping"

    id = Column(String, primary_key=True, index=True)
    client_po_id = Column(String, ForeignKey("client_pos.id"), nullable=False, index=True)
    vendor_po_id = Column(String, ForeignKey("vendor_pos.id"), nullable=False, index=True)
    allocated_value = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    service_component = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("client_po_id", "vendor_po_id", name="uq_client_vendor_po_pair"),
    )

    client_po = relationship("ClientPO", back_populates="allocations")
    vendor_po = relationship("VendorPO", back_populates="mapping_entries")


# ---------------------------------------------------------------------------
# LAYER 3 — Vendor POs  (Cost Layer)
# ---------------------------------------------------------------------------

class VendorPO(Base):
    """
    Cost allocation derived from a Client PO.
    One VendorPO → many VendorInvoices.
    SUM(VendorInvoice.invoice_amount) must not exceed VendorPO.allocated_value.
    """
    __tablename__ = "vendor_pos"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, unique=True)
    vendor_po_number = Column(String, nullable=False, index=True)
    vendor_name = Column(String, nullable=False, index=True)
    client_po_id = Column(String, ForeignKey("client_pos.id"), nullable=True, index=True)
    allocated_value = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    service_description = Column(Text, nullable=True)
    issue_date = Column(DateTime(timezone=True), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="DRAFT")  # DRAFT | APPROVED | ACTIVE | CLOSED
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", foreign_keys=[document_id])
    client_po = relationship("ClientPO", foreign_keys=[client_po_id])
    mapping_entries = relationship("POAllocation", back_populates="vendor_po", cascade="all, delete-orphan")
    vendor_invoices = relationship("VendorInvoice", back_populates="vendor_po")


# ---------------------------------------------------------------------------
# Vendor Invoices  (Cost Actuals)
# ---------------------------------------------------------------------------

class VendorInvoice(Base):
    """
    Invoice from a vendor against a Vendor PO.
    Supports 2-way matching (invoice ↔ VendorPO) and
    3-way matching (invoice ↔ VendorPO ↔ unit_rate × quantity).
    Overbilling is detected when SUM(invoice_amount for vendor_po) > VendorPO.allocated_value.
    """
    __tablename__ = "vendor_invoices"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, unique=True)
    vendor_po_id = Column(String, ForeignKey("vendor_pos.id"), nullable=True, index=True)
    invoice_number = Column(String, nullable=False, index=True)
    vendor_name = Column(String, nullable=False, index=True)
    invoice_amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    invoice_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)

    # 3-way matching
    unit_rate = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    line_items = Column(Text, nullable=True)  # JSON string

    # Validation state
    status = Column(String, default="PENDING")
    # PENDING | APPROVED | PAID | FLAGGED | OVERBILLING_DETECTED
    matching_status = Column(String, nullable=True)
    # TWO_WAY_MATCHED | THREE_WAY_MATCHED | UNMATCHED | DUPLICATE

    overbilling_flag = Column(Boolean, default=False)
    overbilling_amount = Column(Float, nullable=True)
    is_duplicate = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_vendor_inv_name_date", "vendor_name", "invoice_date"),
    )

    document = relationship("Document", foreign_keys=[document_id])
    vendor_po = relationship("VendorPO", back_populates="vendor_invoices")


# ---------------------------------------------------------------------------
# Client Invoices  (Revenue Actuals)
# ---------------------------------------------------------------------------

class ClientInvoice(Base):
    """
    Invoice sent to a client against a Client PO.
    """
    __tablename__ = "client_invoices"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, unique=True)
    client_po_id = Column(String, ForeignKey("client_pos.id"), nullable=True, index=True)
    invoice_number = Column(String, nullable=False, index=True)
    client_name = Column(String, nullable=False, index=True)
    invoice_amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    invoice_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="PENDING")  # PENDING | APPROVED | PAID
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", foreign_keys=[document_id])
    client_po = relationship("ClientPO", back_populates="client_invoices")
