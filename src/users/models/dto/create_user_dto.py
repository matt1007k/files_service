from pydantic.main import BaseModel


class CreateUserDto(BaseModel):
    email: str
    password: str
    username: str
