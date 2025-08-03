from core.util.db_session import db_dependency
from pydantic import BaseModel
from users.repository.user_repository import UserRepository
from core.util.encrypt_provider import EncryptProvider
from users.models.dto.login_dto import LoginDto
from core.util.app_error import AppError
from core.util.jwt_provider import JwtProvider


class UserResponse(BaseModel):
    id: str
    username: str
    email: str


class LoginResponse(BaseModel):
    user: UserResponse
    token: str


class AuthService:
    def __init__(self, db: db_dependency):
        self.user_repository = UserRepository(db)
        self.encrypt_provider = EncryptProvider()
        self.jwt_provider = JwtProvider()

    def login(self, user: LoginDto) -> LoginResponse:
        try:
            user_exists = self.user_repository.get_one_by_email(user.email)
            if not user_exists:
                raise AppError("User not found", status_code=404)

            if not self.encrypt_provider.verify_password(
                user.password, str(user_exists.password)
            ):
                raise AppError("Email/Password is not correct", status_code=400)
            token = self.jwt_provider.create_access_token(
                data={"id": str(user_exists.id), "email": str(user_exists.email)}
            )
            token_decode = self.jwt_provider.decode_access_token(token)
            print(f"{token_decode}")
            return LoginResponse(
                user=UserResponse(
                    id=str(user_exists.id),
                    username=str(user_exists.username),
                    email=str(user_exists.email),
                ),
                token=token,
            )
        except Exception as e:
            print(f"Error AuthService login: {e}")
            raise AppError(str(e), status_code=404)
        except AppError as e:
            print(f"AppError AuthService login: {e}")
            raise AppError(e.message, status_code=e.status_code)
