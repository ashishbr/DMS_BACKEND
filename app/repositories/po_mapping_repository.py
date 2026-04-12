from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import POAllocation
from app.repositories.base_repository import BaseRepository


class POMappingRepository(BaseRepository[POAllocation]):
    def __init__(self, db: Session):
        super().__init__(POAllocation, db)

    def get_by_client_po(self, client_po_id: str) -> List[POAllocation]:
        return (
            self.db.query(POAllocation)
            .filter(POAllocation.client_po_id == client_po_id)
            .all()
        )

    def get_by_vendor_po(self, vendor_po_id: str) -> Optional[POAllocation]:
        """A VendorPO can only belong to one ClientPO (unique constraint)."""
        return (
            self.db.query(POAllocation)
            .filter(POAllocation.vendor_po_id == vendor_po_id)
            .first()
        )

    def get_by_pair(self, client_po_id: str, vendor_po_id: str) -> Optional[POAllocation]:
        return (
            self.db.query(POAllocation)
            .filter(
                POAllocation.client_po_id == client_po_id,
                POAllocation.vendor_po_id == vendor_po_id,
            )
            .first()
        )

    def get_total_allocated(self, client_po_id: str) -> float:
        result = (
            self.db.query(func.sum(POAllocation.allocated_value))
            .filter(POAllocation.client_po_id == client_po_id)
            .scalar()
        )
        return float(result or 0.0)

    def upsert(
        self,
        client_po_id: str,
        vendor_po_id: str,
        allocated_value: float,
        currency: str = "USD",
        service_component: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> POAllocation:
        """Insert or update a mapping entry."""
        existing = self.get_by_pair(client_po_id, vendor_po_id)
        if existing:
            existing.allocated_value = allocated_value
            if currency:
                existing.currency = currency
            if service_component is not None:
                existing.service_component = service_component
            if notes is not None:
                existing.notes = notes
            self.db.flush()
            self.db.refresh(existing)
            return existing

        import uuid
        mapping = POAllocation(
            id=str(uuid.uuid4()),
            client_po_id=client_po_id,
            vendor_po_id=vendor_po_id,
            allocated_value=allocated_value,
            currency=currency,
            service_component=service_component,
            notes=notes,
        )
        self.db.add(mapping)
        self.db.flush()
        self.db.refresh(mapping)
        return mapping
