from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime


# ---------------------------------------------------------------------------
# Document schemas  (existing — extended with pipeline fields)
# ---------------------------------------------------------------------------

class DocumentBase(BaseModel):
    title: str
    category: str
    client: str
    vendor: Optional[str] = None
    amount: float
    currency: str = "USD"
    status: str = "Draft"
    due_date: Optional[datetime] = None
    confidence: float = 0.0
    linked_to: Optional[str] = None
    pdf_url: Optional[str] = None
    po_number: Optional[str] = None
    invoice_number: Optional[str] = None
    msa_number: Optional[str] = None


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    client: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None
    confidence: Optional[float] = None
    linked_to: Optional[str] = None
    pdf_url: Optional[str] = None
    po_number: Optional[str] = None
    invoice_number: Optional[str] = None
    msa_number: Optional[str] = None


class Document(DocumentBase):
    id: str
    created_at: datetime
    file_path: Optional[str] = None
    processed: bool = False
    processing_status: Optional[str] = None
    extracted_json: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Exception schemas  (existing)
# ---------------------------------------------------------------------------

class ExceptionBase(BaseModel):
    document_id: str
    issue: str
    severity: str
    owner: str


class ExceptionCreate(ExceptionBase):
    pass


class ExceptionUpdate(BaseModel):
    issue: Optional[str] = None
    severity: Optional[str] = None
    owner: Optional[str] = None
    resolved: Optional[bool] = None


class Exception(ExceptionBase):
    id: str
    raised_at: datetime
    resolved: bool = False

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Alert schemas  (existing)
# ---------------------------------------------------------------------------

class AlertBase(BaseModel):
    title: str
    description: str
    level: str
    document_id: Optional[str] = None


class AlertCreate(AlertBase):
    pass


class AlertUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    acknowledged: Optional[bool] = None


class Alert(AlertBase):
    id: str
    timestamp: datetime
    acknowledged: bool = False

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Dashboard schemas  (existing)
# ---------------------------------------------------------------------------

class KPIMetric(BaseModel):
    label: str
    value: str
    delta: str
    helper: str


class UtilizationTrend(BaseModel):
    month: str
    client: int
    vendor: int


class CategorySplit(BaseModel):
    name: str
    value: int
    fill: str


class DashboardInsights(BaseModel):
    kpis: List[KPIMetric]
    utilizationTrend: List[UtilizationTrend]
    categorySplit: List[CategorySplit]
    alerts: List[Alert]
    exceptions: List[Exception]


# ---------------------------------------------------------------------------
# Chat schemas  (existing)
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    context: Optional[List[ChatMessage]] = None


class ChatResponse(BaseModel):
    reply: str


# ---------------------------------------------------------------------------
# Upload schemas  (existing)
# ---------------------------------------------------------------------------

class UploadedFile(BaseModel):
    name: str
    size: int
    type: str
    status: str
    location: str


class UploadResponse(BaseModel):
    uploads: List[UploadedFile]


# ---------------------------------------------------------------------------
# Document detail response  (existing)
# ---------------------------------------------------------------------------

class DocumentDetailResponse(BaseModel):
    document: Document
    related_exceptions: List[Exception]
    related_alerts: List[Alert]


# ---------------------------------------------------------------------------
# MSA bucket schemas  (existing)
# ---------------------------------------------------------------------------

class MSABucket(BaseModel):
    msa_number: str
    msa_documents: List[Document]
    po_documents: List[Document]
    invoice_documents: List[Document]
    other_documents: List[Document]
    total_msa_value: float
    total_po_value: float
    total_invoice_value: float
    expires_on: Optional[datetime] = None
    days_until_expiry: Optional[int] = None
    expiring_soon: bool = False


class MSABucketResponse(BaseModel):
    buckets: List[MSABucket]
    unlinked_documents: List[Document]


# ---------------------------------------------------------------------------
# FINANCIAL — Client PO schemas
# ---------------------------------------------------------------------------

class ClientPOCreate(BaseModel):
    document_id: Optional[str] = None
    po_number: str
    client_name: str
    total_value: float
    currency: str = "USD"
    service_scope: Optional[str] = None
    issue_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: str = "DRAFT"
    msa_number: Optional[str] = None


class ClientPOUpdate(BaseModel):
    po_number: Optional[str] = None
    client_name: Optional[str] = None
    total_value: Optional[float] = None
    currency: Optional[str] = None
    service_scope: Optional[str] = None
    issue_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None
    msa_number: Optional[str] = None


class ClientPOResponse(BaseModel):
    id: str
    document_id: Optional[str] = None
    po_number: str
    client_name: str
    total_value: float
    currency: str
    service_scope: Optional[str] = None
    issue_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: str
    msa_number: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# FINANCIAL — Vendor PO schemas
# ---------------------------------------------------------------------------

class VendorPOCreate(BaseModel):
    document_id: str
    vendor_po_number: str
    vendor_name: str
    allocated_value: float
    currency: str = "USD"
    client_po_id: Optional[str] = None
    service_description: Optional[str] = None
    issue_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: str = "DRAFT"


class VendorPOUpdate(BaseModel):
    vendor_po_number: Optional[str] = None
    vendor_name: Optional[str] = None
    allocated_value: Optional[float] = None
    currency: Optional[str] = None
    client_po_id: Optional[str] = None
    service_description: Optional[str] = None
    issue_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None


class VendorPOResponse(BaseModel):
    id: str
    document_id: Optional[str] = None  # nullable: generated POs have no source document
    vendor_po_number: str
    vendor_name: str
    client_po_id: Optional[str] = None
    allocated_value: float
    currency: str
    service_description: Optional[str] = None
    issue_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: str
    is_generated: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# FINANCIAL — POAllocation schemas  (Layer 2 mapping)
# ---------------------------------------------------------------------------

class POAllocationCreate(BaseModel):
    client_po_id: str
    vendor_po_id: str
    allocated_value: float
    currency: str = "USD"
    service_component: Optional[str] = None
    notes: Optional[str] = None


class POAllocationUpdate(BaseModel):
    allocated_value: Optional[float] = None
    currency: Optional[str] = None
    service_component: Optional[str] = None
    notes: Optional[str] = None


class POAllocationResponse(BaseModel):
    id: str
    client_po_id: str
    vendor_po_id: str
    allocated_value: float
    currency: str
    service_component: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class POAllocationWithWarning(BaseModel):
    """Response for POST /po-allocations — includes over-allocation warning."""
    allocation: POAllocationResponse
    warning: bool = False
    over_allocated_by: Optional[float] = None
    available_before: float
    total_allocated_after: float
    client_po_total_value: float


# ---------------------------------------------------------------------------
# FINANCIAL — Vendor Invoice schemas
# ---------------------------------------------------------------------------

class VendorInvoiceCreate(BaseModel):
    document_id: str
    invoice_number: str
    vendor_name: str
    invoice_amount: float
    currency: str = "USD"
    vendor_po_id: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    unit_rate: Optional[float] = None
    quantity: Optional[float] = None
    line_items: Optional[str] = None


class VendorInvoiceUpdate(BaseModel):
    vendor_po_id: Optional[str] = None
    invoice_amount: Optional[float] = None
    currency: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    unit_rate: Optional[float] = None
    quantity: Optional[float] = None
    line_items: Optional[str] = None
    status: Optional[str] = None
    matching_status: Optional[str] = None


class VendorInvoiceResponse(BaseModel):
    id: str
    document_id: str
    vendor_po_id: Optional[str] = None
    invoice_number: str
    vendor_name: str
    invoice_amount: float
    currency: str
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    unit_rate: Optional[float] = None
    quantity: Optional[float] = None
    line_items: Optional[str] = None
    status: str
    matching_status: Optional[str] = None
    overbilling_flag: bool
    overbilling_amount: Optional[float] = None
    is_duplicate: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# FINANCIAL — Client Invoice schemas
# ---------------------------------------------------------------------------

class ClientInvoiceCreate(BaseModel):
    document_id: str
    invoice_number: str
    client_name: str
    invoice_amount: float
    currency: str = "USD"
    client_po_id: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None


class ClientInvoiceUpdate(BaseModel):
    client_po_id: Optional[str] = None
    invoice_amount: Optional[float] = None
    currency: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = None


class ClientInvoiceResponse(BaseModel):
    id: str
    document_id: str
    client_po_id: Optional[str] = None
    invoice_number: str
    client_name: str
    invoice_amount: float
    currency: str
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# FINANCIAL — Margin & Lineage response schemas
# ---------------------------------------------------------------------------

class MarginSummary(BaseModel):
    client_po_id: str
    po_number: str
    client_name: str
    total_value: float
    total_allocated: float
    margin: float
    margin_pct: float
    vendor_count: int
    over_allocated: bool
    over_allocated_by: Optional[float] = None
    currency: str


class VendorPOWithInvoices(BaseModel):
    vendor_po: VendorPOResponse
    allocated_value: float
    total_invoiced: float
    remaining: float
    utilization_pct: float
    invoices: List[VendorInvoiceResponse]


class ClientPOLineage(BaseModel):
    client_po: ClientPOResponse
    margin: MarginSummary
    vendor_allocations: List[VendorPOWithInvoices]


# ---------------------------------------------------------------------------
# FINANCIAL — Consumption & Billing Violation schemas
# ---------------------------------------------------------------------------

class VendorPOConsumption(BaseModel):
    vendor_po_id: str
    vendor_po_number: str
    vendor_name: str
    allocated_value: float
    total_invoiced: float
    remaining: float
    utilization_pct: float
    is_overbilled: bool
    overbilled_by: Optional[float] = None
    invoice_count: int
    currency: str


class BillingViolation(BaseModel):
    violation_type: str  # VENDOR_PO_OVERBILLED | CLIENT_PO_OVER_ALLOCATED
    entity_id: str
    entity_ref: str      # po_number or vendor_po_number
    cap_value: float
    actual_value: float
    excess: float
    currency: str


class BillingViolationsResponse(BaseModel):
    vendor_po_violations: List[BillingViolation]
    client_po_violations: List[BillingViolation]
    total_violations: int


class GlobalMarginSummary(BaseModel):
    client_pos: List[MarginSummary]
    total_revenue_committed: float
    total_cost_allocated: float
    total_margin: float
    overall_margin_pct: float
    over_allocated_pos: int


# ---------------------------------------------------------------------------
# FINANCIAL — Clients Overview (hierarchical view)
# ---------------------------------------------------------------------------

class VendorWithInvoices(BaseModel):
    vendor_name: str
    vendor_pos: List[VendorPOResponse]
    total_allocated: float
    total_invoiced: float
    invoices: List[VendorInvoiceResponse]


class LinkedDocumentSummary(BaseModel):
    id: str
    title: str
    category: str
    amount: float
    currency: str
    status: str
    po_number: Optional[str] = None
    invoice_number: Optional[str] = None
    msa_number: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ClientWithVendors(BaseModel):
    client_name: str
    total_po_value: float
    total_client_invoiced: float
    client_pos: List[ClientPOResponse]
    client_invoices: List[ClientInvoiceResponse]
    vendors: List[VendorWithInvoices]
    linked_documents: List[LinkedDocumentSummary] = []


class ClientsOverviewResponse(BaseModel):
    clients: List[ClientWithVendors]
    total_clients: int


# ---------------------------------------------------------------------------
# Vendor PO Generator — standalone generated POs with PDF
# ---------------------------------------------------------------------------

class VendorPOItemCreate(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: Optional[float] = None  # auto-computed as quantity * unit_price if omitted


class VendorPOItemResponse(BaseModel):
    id: str
    vendor_po_id: str
    description: str
    quantity: float
    unit_price: float
    total_price: float

    class Config:
        from_attributes = True


class GeneratedVendorPOCreate(BaseModel):
    vendor_name: str
    vendor_address: Optional[str] = None
    vendor_email: Optional[str] = None
    vendor_phone: Optional[str] = None
    client_name: Optional[str] = None     # client this PO is generated under
    po_number: Optional[str] = None       # auto-generated if omitted
    issue_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    payment_terms: Optional[str] = None
    line_items: List[VendorPOItemCreate]
    subtotal: Optional[float] = None      # computed from items if omitted
    tax: float = 0.0
    discount: float = 0.0
    total_amount: Optional[float] = None  # computed if omitted
    notes: Optional[str] = None
    created_by: Optional[str] = None


class GeneratedVendorPOUpdate(BaseModel):
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_email: Optional[str] = None
    vendor_phone: Optional[str] = None
    client_name: Optional[str] = None
    delivery_date: Optional[datetime] = None
    payment_terms: Optional[str] = None
    line_items: Optional[List[VendorPOItemCreate]] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    discount: Optional[float] = None
    total_amount: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class GeneratedVendorPOResponse(BaseModel):
    id: str
    po_number: str
    vendor_name: str
    vendor_address: Optional[str] = None
    vendor_email: Optional[str] = None
    vendor_phone: Optional[str] = None
    client_name: Optional[str] = None
    vendor_po_id: Optional[str] = None   # ID of the linked VendorPO in the financial layer
    issue_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    payment_terms: Optional[str] = None
    subtotal: float
    tax: float
    discount: float
    total_amount: float
    notes: Optional[str] = None
    pdf_path: Optional[str] = None
    status: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[VendorPOItemResponse] = []

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Client rename
# ---------------------------------------------------------------------------

class ClientRenameRequest(BaseModel):
    new_name: str


class ClientCreateRequest(BaseModel):
    client_name: str
    currency: str = "USD"
    service_scope: Optional[str] = None
    msa_number: Optional[str] = None


# ---------------------------------------------------------------------------
# Document link / unlink / category
# ---------------------------------------------------------------------------

class DocumentLinkRequest(BaseModel):
    client_name: str
    linked_by: Optional[str] = None  # user/role from frontend auth context


class DocumentCategoryUpdate(BaseModel):
    category: str


class DocumentClientLinkRecord(BaseModel):
    id: str
    document_id: str
    client_name: str
    linked_at: datetime
    unlinked_at: Optional[datetime] = None
    is_active: bool
    linked_by: Optional[str] = None

    class Config:
        from_attributes = True
