

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str
    
class LoginSchema(BaseModel):
    email: str
    password: str