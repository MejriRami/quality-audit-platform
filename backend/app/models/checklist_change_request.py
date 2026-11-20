from datetime import datetime

from sqlalchemy import Column, ForeignKey, Integer, String, Text, TIMESTAMP, Index
from sqlalchemy.orm import relationship

from app.config.database import Base


class ChecklistChangeRequest(Base):
    __tablename__ = "checklist_change_requests"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(32), nullable=False)  # questionnaire | question
    action_type = Column(String(32), nullable=False)  # create | update | delete
    status = Column(String(32), nullable=False, default="pending")  # pending | approved | rejected

    questionnaire_id = Column(
        Integer, ForeignKey("questionnaires.id", ondelete="SET NULL"), nullable=True
    )
    target_id = Column(Integer, nullable=True)  # questionnaire.id or question.id depending on entity_type
    payload = Column(Text, nullable=True)  # JSON payload as text

    requested_by_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    request_comment = Column(Text, nullable=True)
    review_comment = Column(Text, nullable=True)

    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)
    reviewed_at = Column(TIMESTAMP, nullable=True)
    applied_at = Column(TIMESTAMP, nullable=True)

    requested_by = relationship("User", foreign_keys=[requested_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    questionnaire = relationship("Questionnaire", foreign_keys=[questionnaire_id])

    __table_args__ = (
        Index("ix_checklist_change_requests_status_created", "status", "created_at"),
        Index("ix_checklist_change_requests_requested_by", "requested_by_id"),
        Index("ix_checklist_change_requests_questionnaire", "questionnaire_id"),
    )
