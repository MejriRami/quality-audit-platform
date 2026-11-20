from pydantic import BaseModel
from typing import Optional


class FrameworkBase(BaseModel):
    code: str
    label: str

class FrameworkCreate(FrameworkBase):
    pass

class FrameworkUpdate(BaseModel):
    code : Optional [str] = None
    label : Optional [str]= None

class FrameworkOut(BaseModel):
    id: int
    code: str
    label: str

    model_config = {"from_attributes": True}
