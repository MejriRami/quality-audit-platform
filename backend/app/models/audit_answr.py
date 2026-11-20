from sqlalchemy import Column, Integer, Boolean, Text,String, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base


class AuditAnswer(Base):
    __tablename__ = "audit_answers"

    id = Column(Integer, primary_key=True)
    audit_id = Column(Integer, ForeignKey("audits.id"))
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    identifier= Column(String(20), unique=True)
    value = Column(Integer, nullable=False)
    finding_text = Column(Text)
    # Open audits: the question the auditor typed (no Question row).
    question_text = Column(Text, nullable=True)
    fail = Column(Boolean)
    improve = Column(Boolean)
    pass_ = Column(Boolean, name='pass')
    process = Column(String)
    standard_paragraph = Column(String)
    classification = Column(String)
    silent_box = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(TIMESTAMP(timezone=True))

    audit = relationship("Audit", back_populates="answers")
    question = relationship("Question", back_populates="answers")
    documents = relationship("Document", back_populates="answer")
    requirements = relationship("AuditAnswerRequirement", back_populates="audit_answer")
