from sqlalchemy import Column, Date, DateTime, Integer, String, UniqueConstraint, func

from app.config.database import Base


class PlantHoliday(Base):
    __tablename__ = "plant_holidays"
    __table_args__ = (
        UniqueConstraint("plant", "holiday_date", name="uq_plant_holidays_plant_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    plant = Column(String(80), nullable=False, index=True)
    holiday_date = Column(Date, nullable=False, index=True)
    name = Column(String(150), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
