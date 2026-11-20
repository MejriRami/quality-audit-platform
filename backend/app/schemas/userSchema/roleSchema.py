from pydantic import BaseModel

class RoleBase(BaseModel):
    name: str


class RoleResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class RoleCreate(RoleBase):
    pass

class RoleUpdate(BaseModel):
    name: str

class RoleOut(RoleBase):
    id: int
    model_config = {"from_attributes": True}

class RoleAssignmentRequest(BaseModel):
    user_email: str
    role_name: str