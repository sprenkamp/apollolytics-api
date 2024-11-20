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

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'request_time': self.request_time,
            'model_name': self.model_name,
            'text': self.text,
            'contextualize': self.contextualize,
            'result': self.result
        }
