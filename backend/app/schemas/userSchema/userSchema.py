from pydantic import BaseModel, Field
from typing import Optional

class UserBase(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str = Field(..., max_length=72)

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None

class UserOut(UserBase):
    id: int

    model_config = {"from_attributes": True}

class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    active: bool

    model_config = {
        "from_attributes": True
}
    
class UserUpdatePasswordResponse(BaseModel):
    message: str

    model_config = {
        "from_attributes": True
}
    
class UserUpdatePassword(BaseModel):
    email: str
    new_password: str
    confirm_password: str
    
class UserAuditorBase(BaseModel):
    id: int
    email: str

    class Config:
        orm_mode = True  
