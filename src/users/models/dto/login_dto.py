from pydantic.main import BaseModel


class LoginDto(BaseModel):
    email: str
    password: str
