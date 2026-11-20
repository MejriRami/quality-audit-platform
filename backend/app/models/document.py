from sqlalchemy import Column, Integer, String, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from app.config.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255))
    mimetype = Column(String(255))
    size = Column(Integer)
    file_url = Column(String(500),nullable=False)
    sharepoint_site_id = Column(String, nullable=True)
    sharepoint_drive_id = Column(String, nullable=True)
    sharepoint_item_id = Column(String, nullable=True)
    sharepoint_path = Column(String, nullable=True)
    audit_answer_id = Column(Integer, ForeignKey("audit_answers.id"))
    corrective_action_id = Column(Integer, ForeignKey("corrective_actions.id"))

    uploaded_at = Column(TIMESTAMP(timezone=True))
    uploaded_by = Column(Integer, ForeignKey("users.id"))

    answer = relationship("AuditAnswer", back_populates="documents")
    corrective_action = relationship("CorrectiveAction")
    uploader = relationship("User")
