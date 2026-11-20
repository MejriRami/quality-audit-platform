from sqlalchemy import Column, Integer, Text, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base
from app.models.enums import ca_decision_enum


class CorrectiveActionHistory(Base):
    __tablename__ = "corrective_action_history"

    id = Column(Integer, primary_key=True)
    corrective_action_id = Column(Integer, ForeignKey("corrective_actions.id"))
    auditor_id = Column(Integer, ForeignKey("users.id"))
    decision = Column(ca_decision_enum)
    comment = Column(Text)
    reviewed_at = Column(TIMESTAMP)

    document_id = Column(Integer, ForeignKey("documents.id"))

    corrective_action = relationship("CorrectiveAction", back_populates="history")
    auditor = relationship("User")
    document = relationship("Document")
