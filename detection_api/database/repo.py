from sqlalchemy.orm import Session

from detection_api.database import AnalysisResult


class Repo:

    def __init__(self, db: Session):
        self.db = db

    def create(self, db_obj):
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)

    def update(self, db_obj):
        self.db.add(db_obj)
        self.db.commit()

    def delete(self, db_obj):
        db_obj.is_deleted = True
        self.db.add(db_obj)
        self.db.commit()

    def hard_delete(self, db_obj):
        self.db.delete(db_obj)
        self.db.commit()

