from typing import Optional
from core.util.db_session import db_dependency
from users.models.user import User


class UserRepository:

    def __init__(self, db: db_dependency):
        self.db = db

    def create_user(self, user: User):
        self.db.add(user)
        self.db.commit()
        return user

    def get_one_by_id(self, id: str) -> Optional[User]:
        try:
            return self.db.query(User).get(id)
        except Exception as e:
            print(f"Error get_one_by_id: {e}")
            return None

    def get_one_by_email(self, email: str) -> Optional[User]:
        try:
            return self.db.query(User).filter(User.email == email).first()
        except Exception as e:
            print(f"Error get_one_by_email: {e}")
            return None

    def get_one_by_username(self, username: str) -> User:
        try:
            return self.db.query(User).filter(User.username == username).first()
        except Exception as e:
            print(f"Error get_one_by_username: {e}")
            return None
