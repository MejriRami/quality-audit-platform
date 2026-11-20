from pydantic import BaseModel

class AuditTypeBase(BaseModel):
    id: int
    value: str

    class Config:
        orm_mode = True

class AuditTypeCreate(BaseModel):
    value: str