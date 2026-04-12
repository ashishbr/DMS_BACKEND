from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import ClientPO, POAllocation
from app.repositories.base_repository import BaseRepository


class ClientPORepository(BaseRepository[ClientPO]):
    def __init__(self, db: Session):
        super().__init__(ClientPO, db)

    def get_by_po_number(self, po_number: str) -> Optional[ClientPO]:
        return (
            self.db.query(ClientPO)
            .filter(ClientPO.po_number == po_number)
            .first()
        )

    def get_by_document_id(self, document_id: str) -> Optional[ClientPO]:
        return (
            self.db.query(ClientPO)
            .filter(ClientPO.document_id == document_id)
            .first()
        )

    def get_by_client_name(self, client_name: str) -> List[ClientPO]:
        return (
            self.db.query(ClientPO)
            .filter(ClientPO.client_name.ilike(f"%{client_name}%"))
            .all()
        )

    def get_total_allocated(self, client_po_id: str) -> float:
        """Return SUM(allocated_value) from the mapping table for this Client PO."""
        result = (
            self.db.query(func.sum(POAllocation.allocated_value))
            .filter(POAllocation.client_po_id == client_po_id)
            .scalar()
        )
        return float(result or 0.0)

    def get_with_allocations(self, client_po_id: str) -> Optional[ClientPO]:
        """Load a ClientPO with its allocations eagerly."""
        from sqlalchemy.orm import joinedload
        return (
            self.db.query(ClientPO)
            .options(joinedload(ClientPO.allocations))
            .filter(ClientPO.id == client_po_id)
            .first()
        )

    def get_all_with_margin(self, skip: int = 0, limit: int = 100) -> List[ClientPO]:
        return self.db.query(ClientPO).offset(skip).limit(limit).all()
