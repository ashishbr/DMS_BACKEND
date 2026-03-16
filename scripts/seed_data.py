# #!/usr/bin/env python3
# """
# Script to populate the database with sample data
# """
# import sys
# import os
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# from sqlalchemy.orm import Session
# from app.database import SessionLocal, engine
# from app.models import Base, Document, Exception, Alert
# from datetime import datetime, timedelta
# import uuid

# def create_sample_data():
#     # Create all tables
#     Base.metadata.create_all(bind=engine)
    
#     db = SessionLocal()
    
#     try:
#         # Clear existing data
#         db.query(Alert).delete()
#         db.query(Exception).delete()
#         db.query(Document).delete()
        
#         # Create sample documents
#         documents = [
#             Document(
#                 id="PO-2024-001",
#                 title="EMB Retail Supply PO",
#                 category="Client PO",
#                 client="EMB Retail",
#                 amount=150000,
#                 currency="USD",
#                 status="Approved",
#                 created_at=datetime(2024, 3, 2, 9, 30, 0),
#                 due_date=datetime(2024, 12, 31),
#                 confidence=0.98,
#                 linked_to="AGR-2024-002",
#                 pdf_url="/uploads/sample-po.pdf",
#                 processed=True
#             ),
#             Document(
#                 id="INV-2024-032",
#                 title="Supplier Invoice - Batch #32",
#                 category="Vendor Invoice",
#                 client="EMB Retail",
#                 vendor="Northwind Components",
#                 amount=28500,
#                 currency="USD",
#                 status="Pending Review",
#                 created_at=datetime(2024, 3, 11, 14, 47, 0),
#                 confidence=0.91,
#                 linked_to="PO-2024-001",
#                 pdf_url="/uploads/sample-invoice.pdf",
#                 processed=True
#             ),
#             Document(
#                 id="AGR-2024-002",
#                 title="Service Agreement - Field Support",
#                 category="Service Agreement",
#                 client="EMB Logistics",
#                 vendor="Helios Services",
#                 amount=56000,
#                 currency="USD",
#                 status="Approved",
#                 created_at=datetime(2024, 1, 17, 10, 15, 0),
#                 due_date=datetime(2025, 1, 17),
#                 confidence=0.95,
#                 pdf_url="/uploads/sample-agreement.pdf",
#                 processed=True
#             ),
#             Document(
#                 id="INV-2024-045",
#                 title="Client Invoice - Retail Expansion",
#                 category="Client Invoice",
#                 client="EMB Retail",
#                 amount=72000,
#                 currency="USD",
#                 status="Flagged",
#                 created_at=datetime(2024, 3, 15, 8, 12, 0),
#                 confidence=0.76,
#                 linked_to="PO-2023-014",
#                 pdf_url="/uploads/sample-invoice.pdf",
#                 processed=True
#             ),
#             Document(
#                 id="PO-2023-014",
#                 title="Vendor Supply PO",
#                 category="Vendor PO",
#                 client="EMB Retail",
#                 vendor="Helios Services",
#                 amount=90000,
#                 currency="USD",
#                 status="Approved",
#                 created_at=datetime(2023, 11, 21, 12, 0, 0),
#                 confidence=0.99,
#                 pdf_url="/uploads/sample-po.pdf",
#                 processed=True
#             )
#         ]
        
#         for doc in documents:
#             db.add(doc)
        
#         # Create sample exceptions
#         exceptions = [
#             Exception(
#                 id="EX-220",
#                 document_id="INV-2024-045",
#                 issue="Invoice exceeds PO cap by 8%",
#                 severity="high",
#                 owner="Finance Ops",
#                 raised_at=datetime(2024, 3, 16, 9, 4, 0),
#                 resolved=False
#             ),
#             Exception(
#                 id="EX-221",
#                 document_id="INV-2024-032",
#                 issue="Missing tax registration ID",
#                 severity="medium",
#                 owner="Compliance",
#                 raised_at=datetime(2024, 3, 15, 15, 10, 0),
#                 resolved=False
#             ),
#             Exception(
#                 id="EX-224",
#                 document_id="PO-2024-001",
#                 issue="Vendor address mismatch against CRM record",
#                 severity="low",
#                 owner="Finance Ops",
#                 raised_at=datetime(2024, 3, 13, 11, 22, 0),
#                 resolved=False
#             )
#         ]
        
#         for exc in exceptions:
#             db.add(exc)
        
#         # Create sample alerts
#         alerts = [
#             Alert(
#                 id="AL-400",
#                 title="PO Cap Utilization at 85%",
#                 description="Client PO PO-2024-001 is close to its spending limit. Review pending invoices.",
#                 level="warning",
#                 timestamp=datetime(2024, 3, 16, 11, 32, 0),
#                 acknowledged=False,
#                 document_id="PO-2024-001"
#             ),
#             Alert(
#                 id="AL-404",
#                 title="Service Agreement expiring in 30 days",
#                 description="Agreement AGR-2024-002 for Helios Services expires soon. Consider renewal.",
#                 level="info",
#                 timestamp=datetime(2024, 3, 15, 6, 18, 0),
#                 acknowledged=False,
#                 document_id="AGR-2024-002"
#             ),
#             Alert(
#                 id="AL-409",
#                 title="Unlinked Vendor Invoice",
#                 description="Vendor invoice INV-2024-051 could not be linked automatically.",
#                 level="critical",
#                 timestamp=datetime(2024, 3, 12, 20, 2, 0),
#                 acknowledged=False
#             )
#         ]
        
#         for alert in alerts:
#             db.add(alert)
        
#         db.commit()
#         print("Sample data created successfully!")
        
#     except Exception as e:
#         db.rollback()
#         print(f"Error creating sample data: {e}")
#         raise
#     finally:
#         db.close()

# if __name__ == "__main__":
#     create_sample_data()

#!/usr/bin/env python3
"""
Script to populate the database with sample data
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import Base, Document, Exception, Alert, ClientPO, POAllocation, VendorPO, VendorInvoice, ClientInvoice
from datetime import datetime, timedelta
import uuid

def create_sample_data():
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Clear existing data (order matters due to FK constraints)
        db.query(POAllocation).delete()
        db.query(VendorInvoice).delete()
        db.query(ClientInvoice).delete()
        db.query(VendorPO).delete()
        db.query(ClientPO).delete()
        db.query(Alert).delete()
        db.query(Exception).delete()
        db.query(Document).delete()

        # ---------------------------------------------------------------
        # Documents
        # ---------------------------------------------------------------
        documents = [
            Document(
                id="DOC-CPO-001",
                title="EMB Retail Supply PO",
                category="Client PO",
                client="EMB Retail",
                amount=150000,
                currency="USD",
                status="Approved",
                created_at=datetime(2024, 3, 2, 9, 30, 0),
                due_date=datetime(2024, 12, 31),
                confidence=0.98,
                linked_to="AGR-2024-002",
                pdf_url="/uploads/sample-po.pdf",
                processed=True,
                po_number="CPO-2024-001",
                processing_status="VALIDATED",
            ),
            Document(
                id="DOC-CPO-002",
                title="EMB Logistics Field Support PO",
                category="Client PO",
                client="EMB Logistics",
                amount=80000,
                currency="USD",
                status="Approved",
                created_at=datetime(2024, 1, 10, 8, 0, 0),
                due_date=datetime(2024, 12, 31),
                confidence=0.97,
                pdf_url="/uploads/sample-po-2.pdf",
                processed=True,
                po_number="CPO-2024-002",
                processing_status="VALIDATED",
            ),
            Document(
                id="DOC-VPO-001",
                title="Vendor Supply PO - Northwind",
                category="Vendor PO",
                client="EMB Retail",
                vendor="Northwind Components",
                amount=90000,
                currency="USD",
                status="Approved",
                created_at=datetime(2023, 11, 21, 12, 0, 0),
                confidence=0.99,
                pdf_url="/uploads/sample-vpo.pdf",
                processed=True,
                po_number="VPO-2024-001",
                processing_status="VALIDATED",
            ),
            Document(
                id="DOC-VPO-002",
                title="Vendor PO - Helios Services",
                category="Vendor PO",
                client="EMB Logistics",
                vendor="Helios Services",
                amount=56000,
                currency="USD",
                status="Approved",
                created_at=datetime(2024, 1, 17, 10, 15, 0),
                due_date=datetime(2025, 1, 17),
                confidence=0.95,
                pdf_url="/uploads/sample-vpo-2.pdf",
                processed=True,
                po_number="VPO-2024-002",
                processing_status="VALIDATED",
            ),
            Document(
                id="DOC-VINV-001",
                title="Supplier Invoice - Batch #32",
                category="Vendor Invoice",
                client="EMB Retail",
                vendor="Northwind Components",
                amount=28500,
                currency="USD",
                status="Pending Review",
                created_at=datetime(2024, 3, 11, 14, 47, 0),
                confidence=0.91,
                linked_to="DOC-VPO-001",
                pdf_url="/uploads/sample-invoice.pdf",
                processed=True,
                invoice_number="VINV-2024-032",
                processing_status="VALIDATED",
            ),
            Document(
                id="DOC-VINV-002",
                title="Supplier Invoice - Batch #33",
                category="Vendor Invoice",
                client="EMB Retail",
                vendor="Northwind Components",
                amount=31000,
                currency="USD",
                status="Approved",
                created_at=datetime(2024, 3, 25, 10, 0, 0),
                confidence=0.94,
                linked_to="DOC-VPO-001",
                pdf_url="/uploads/sample-invoice-2.pdf",
                processed=True,
                invoice_number="VINV-2024-033",
                processing_status="VALIDATED",
            ),
            Document(
                id="DOC-CINV-001",
                title="Client Invoice - Retail Expansion",
                category="Client Invoice",
                client="EMB Retail",
                amount=72000,
                currency="USD",
                status="Flagged",
                created_at=datetime(2024, 3, 15, 8, 12, 0),
                confidence=0.76,
                linked_to="DOC-CPO-001",
                pdf_url="/uploads/sample-client-invoice.pdf",
                processed=True,
                invoice_number="CINV-2024-045",
                processing_status="VALIDATED",
            ),
            Document(
                id="DOC-CINV-002",
                title="Client Invoice - Logistics Q1",
                category="Client Invoice",
                client="EMB Logistics",
                amount=40000,
                currency="USD",
                status="Approved",
                created_at=datetime(2024, 2, 28, 9, 0, 0),
                confidence=0.96,
                linked_to="DOC-CPO-002",
                pdf_url="/uploads/sample-client-invoice-2.pdf",
                processed=True,
                invoice_number="CINV-2024-046",
                processing_status="VALIDATED",
            ),
        ]

        for doc in documents:
            db.add(doc)
        db.flush()  # Flush so FKs resolve below

        # ---------------------------------------------------------------
        # Layer 1 — Client POs
        # ---------------------------------------------------------------
        client_pos = [
            ClientPO(
                id="CPO-001",
                document_id="DOC-CPO-001",
                po_number="CPO-2024-001",
                client_name="EMB Retail",
                total_value=150000,
                currency="USD",
                service_scope="Supply chain management and retail distribution services for FY2024.",
                issue_date=datetime(2024, 3, 1),
                start_date=datetime(2024, 3, 2),
                end_date=datetime(2024, 12, 31),
                status="ACTIVE",
                msa_number="MSA-2023-010",
            ),
            ClientPO(
                id="CPO-002",
                document_id="DOC-CPO-002",
                po_number="CPO-2024-002",
                client_name="EMB Logistics",
                total_value=80000,
                currency="USD",
                service_scope="Field support and on-site logistics management.",
                issue_date=datetime(2024, 1, 8),
                start_date=datetime(2024, 1, 10),
                end_date=datetime(2024, 12, 31),
                status="ACTIVE",
                msa_number="MSA-2023-011",
            ),
        ]

        for cpo in client_pos:
            db.add(cpo)
        db.flush()

        # ---------------------------------------------------------------
        # Layer 3 — Vendor POs (must exist before POAllocation)
        # ---------------------------------------------------------------
        vendor_pos = [
            VendorPO(
                id="VPO-001",
                document_id="DOC-VPO-001",
                vendor_po_number="VPO-2024-001",
                vendor_name="Northwind Components",
                client_po_id="CPO-001",
                allocated_value=90000,
                currency="USD",
                service_description="Component supply and warehousing for EMB Retail distribution network.",
                issue_date=datetime(2023, 11, 20),
                start_date=datetime(2023, 11, 21),
                end_date=datetime(2024, 12, 31),
                status="ACTIVE",
            ),
            VendorPO(
                id="VPO-002",
                document_id="DOC-VPO-002",
                vendor_po_number="VPO-2024-002",
                vendor_name="Helios Services",
                client_po_id="CPO-002",
                allocated_value=56000,
                currency="USD",
                service_description="Field technician deployment and on-site support for EMB Logistics.",
                issue_date=datetime(2024, 1, 15),
                start_date=datetime(2024, 1, 17),
                end_date=datetime(2025, 1, 17),
                status="ACTIVE",
            ),
        ]

        for vpo in vendor_pos:
            db.add(vpo)
        db.flush()

        # ---------------------------------------------------------------
        # Layer 2 — POAllocations (Client PO → Vendor PO mapping)
        # ---------------------------------------------------------------
        allocations = [
            POAllocation(
                id="ALLOC-001",
                client_po_id="CPO-001",
                vendor_po_id="VPO-001",
                allocated_value=90000,
                currency="USD",
                service_component="Component Supply",
                notes="Primary vendor allocation for EMB Retail supply chain.",
            ),
            POAllocation(
                id="ALLOC-002",
                client_po_id="CPO-002",
                vendor_po_id="VPO-002",
                allocated_value=56000,
                currency="USD",
                service_component="Field Support",
                notes="Full allocation to Helios for on-site logistics support.",
            ),
        ]

        for alloc in allocations:
            db.add(alloc)
        db.flush()

        # ---------------------------------------------------------------
        # Vendor Invoices
        # ---------------------------------------------------------------
        vendor_invoices = [
            VendorInvoice(
                id="VINV-001",
                document_id="DOC-VINV-001",
                vendor_po_id="VPO-001",
                invoice_number="VINV-2024-032",
                vendor_name="Northwind Components",
                invoice_amount=28500,
                currency="USD",
                invoice_date=datetime(2024, 3, 10),
                due_date=datetime(2024, 4, 10),
                unit_rate=950.0,
                quantity=30.0,
                line_items='[{"description": "Widget A", "qty": 20, "unit_rate": 950, "total": 19000}, {"description": "Widget B", "qty": 10, "unit_rate": 950, "total": 9500}]',
                status="PENDING",
                matching_status="THREE_WAY_MATCHED",
                overbilling_flag=False,
                is_duplicate=False,
            ),
            VendorInvoice(
                id="VINV-002",
                document_id="DOC-VINV-002",
                vendor_po_id="VPO-001",
                invoice_number="VINV-2024-033",
                vendor_name="Northwind Components",
                invoice_amount=31000,
                currency="USD",
                invoice_date=datetime(2024, 3, 24),
                due_date=datetime(2024, 4, 24),
                unit_rate=950.0,
                quantity=32.0,
                line_items='[{"description": "Widget A", "qty": 32, "unit_rate": 968.75, "total": 31000}]',
                status="APPROVED",
                matching_status="TWO_WAY_MATCHED",
                overbilling_flag=False,
                is_duplicate=False,
            ),
        ]

        for vinv in vendor_invoices:
            db.add(vinv)
        db.flush()

        # ---------------------------------------------------------------
        # Client Invoices
        # ---------------------------------------------------------------
        client_invoices = [
            ClientInvoice(
                id="CINV-001",
                document_id="DOC-CINV-001",
                client_po_id="CPO-001",
                invoice_number="CINV-2024-045",
                client_name="EMB Retail",
                invoice_amount=72000,
                currency="USD",
                invoice_date=datetime(2024, 3, 14),
                due_date=datetime(2024, 4, 14),
                status="PENDING",
            ),
            ClientInvoice(
                id="CINV-002",
                document_id="DOC-CINV-002",
                client_po_id="CPO-002",
                invoice_number="CINV-2024-046",
                client_name="EMB Logistics",
                invoice_amount=40000,
                currency="USD",
                invoice_date=datetime(2024, 2, 27),
                due_date=datetime(2024, 3, 27),
                status="APPROVED",
            ),
        ]

        for cinv in client_invoices:
            db.add(cinv)
        db.flush()

        # ---------------------------------------------------------------
        # Exceptions
        # ---------------------------------------------------------------
        exceptions = [
            Exception(
                id="EX-220",
                document_id="DOC-CINV-001",
                issue="Invoice exceeds PO cap by 8%",
                severity="high",
                owner="Finance Ops",
                raised_at=datetime(2024, 3, 16, 9, 4, 0),
                resolved=False,
            ),
            Exception(
                id="EX-221",
                document_id="DOC-VINV-001",
                issue="Missing tax registration ID on vendor invoice",
                severity="medium",
                owner="Compliance",
                raised_at=datetime(2024, 3, 15, 15, 10, 0),
                resolved=False,
            ),
            Exception(
                id="EX-224",
                document_id="DOC-CPO-001",
                issue="Vendor address mismatch against CRM record",
                severity="low",
                owner="Finance Ops",
                raised_at=datetime(2024, 3, 13, 11, 22, 0),
                resolved=False,
            ),
        ]

        for exc in exceptions:
            db.add(exc)

        # ---------------------------------------------------------------
        # Alerts
        # ---------------------------------------------------------------
        alerts = [
            Alert(
                id="AL-400",
                title="PO Cap Utilization at 85%",
                description="Client PO CPO-2024-001 is close to its spending limit. Review pending invoices.",
                level="warning",
                timestamp=datetime(2024, 3, 16, 11, 32, 0),
                acknowledged=False,
                document_id="DOC-CPO-001",
            ),
            Alert(
                id="AL-404",
                title="Vendor PO nearing full allocation",
                description="VPO-2024-001 has $59,500 invoiced against a $90,000 allocation (66%). Monitor remaining spend.",
                level="info",
                timestamp=datetime(2024, 3, 25, 6, 18, 0),
                acknowledged=False,
                document_id="DOC-VPO-001",
            ),
            Alert(
                id="AL-409",
                title="Unlinked Vendor Invoice",
                description="Vendor invoice VINV-2024-051 could not be linked automatically to any Vendor PO.",
                level="critical",
                timestamp=datetime(2024, 3, 12, 20, 2, 0),
                acknowledged=False,
            ),
        ]

        for alert in alerts:
            db.add(alert)

        db.commit()
        print("Sample data created successfully!")

    except Exception as e:
        db.rollback()
        print(f"Error creating sample data: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    create_sample_data()

