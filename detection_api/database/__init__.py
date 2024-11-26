# Import all the models, so that Base has them before being imported by Alembic

from database.base import Base
from database.models import AnalysisResult