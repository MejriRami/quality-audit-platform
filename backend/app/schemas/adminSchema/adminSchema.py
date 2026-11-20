from datetime import date
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class AdminUserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    active: bool = True
    role_names: list[str] = Field(default_factory=list)


class AdminUserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=72)
    active: Optional[bool] = None
    role_names: Optional[list[str]] = None


class AdminUserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    active: bool
    role_names: list[str] = Field(default_factory=list)


class AdminRoleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)


class AdminRoleUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)


class AdminRoleResponse(BaseModel):
    id: int
    name: str


class PlantHolidayCreate(BaseModel):
    plant: str
    holiday_date: date
    name: Optional[str] = None


class PlantHolidayResponse(BaseModel):
    id: int
    plant: str
    holiday_date: date
    name: Optional[str] = None


class SchedulerRunRequest(BaseModel):
    days_before: int = Field(..., ge=1, le=30)
