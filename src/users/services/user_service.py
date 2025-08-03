from core.util.db_session import db_dependency
from users.repository.user_repository import UserRepository
from users.models.user import User
from core.util.encrypt_provider import EncryptProvider
from users.models.dto.create_user_dto import CreateUserDto
from core.util.app_error import AppError


class UserService:
    def __init__(self, db: db_dependency):
        self.user_repository = UserRepository(db)
        self.encrypt_provider = EncryptProvider()

    def create_user(self, user: CreateUserDto) -> User:
        try:
            if self.user_repository.get_one_by_email(user.email):
                raise AppError("User already exists", status_code=400)
            if self.user_repository.get_one_by_username(user.username):
                raise AppError("User already exists", status_code=400)
            user.password = self.encrypt_provider.get_password_hash(user.password)
            return self.user_repository.create_user(User(**user.dict()))
        except Exception as e:
            print(f"Error UserService create_user: {e}")
            raise AppError(str(e), status_code=400)
