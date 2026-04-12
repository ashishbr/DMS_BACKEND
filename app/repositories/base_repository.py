"""
Generic typed base repository.
All domain repositories extend this class.
Business logic stays in the service layer — repositories only handle DB access.
"""
from typing import Generic, TypeVar, Type, Optional, List, Any, Dict
from sqlalchemy.orm import Session
from app.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get(self, record_id: str) -> Optional[ModelType]:
        return self.db.query(self.model).filter(self.model.id == record_id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def exists(self, record_id: str) -> bool:
        return self.db.query(self.model).filter(self.model.id == record_id).count() > 0

    def create(self, obj: ModelType) -> ModelType:
        self.db.add(obj)
        self.db.flush()       # get the id without committing
        self.db.refresh(obj)
        return obj

    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[ModelType]:
        record = self.get(record_id)
        if not record:
            return None
        for field, value in data.items():
            if hasattr(record, field):
                setattr(record, field, value)
        self.db.flush()
        self.db.refresh(record)
        return record

    def delete(self, record_id: str) -> bool:
        record = self.get(record_id)
        if not record:
            return False
        self.db.delete(record)
        self.db.flush()
        return True

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()
