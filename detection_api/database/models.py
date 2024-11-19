from database.base import Base
from sqlalchemy import Column, String, DateTime, Text, func


class AnalysisResult(Base):
    __tablename__ = 'analysis_results'

    user_id = Column(String, primary_key=True)
    request_time = Column(DateTime(timezone=True), server_default=func.now())  # Current time
    model_name = Column(String)
    text = Column(Text)
    contextualize = Column(String)
    result = Column(Text)  # Store the result as a JSON string
