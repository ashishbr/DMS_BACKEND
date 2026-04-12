from typing import Optional, List
from sqlalchemy.orm import Session
from app.models import ClientInvoice
from app.repositories.base_repository import BaseRepository


class ClientInvoiceRepository(BaseRepository[ClientInvoice]):
    def __init__(self, db: Session):
        super().__init__(ClientInvoice, db)

    def get_by_document_id(self, document_id: str) -> Optional[ClientInvoice]:
        return (
            self.db.query(ClientInvoice)
            .filter(ClientInvoice.document_id == document_id)
            .first()
        )

    def get_by_client_po(self, client_po_id: str) -> List[ClientInvoice]:
        return (
            self.db.query(ClientInvoice)
            .filter(ClientInvoice.client_po_id == client_po_id)
            .all()
        )

    def get_unlinked(self) -> List[ClientInvoice]:
        return (
            self.db.query(ClientInvoice)
            .filter(ClientInvoice.client_po_id.is_(None))
            .all()
        )

    def get_by_invoice_number(self, invoice_number: str) -> Optional[ClientInvoice]:
        return (
            self.db.query(ClientInvoice)
            .filter(ClientInvoice.invoice_number == invoice_number)
            .first()
        )
