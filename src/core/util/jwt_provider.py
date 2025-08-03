from core.util.app_error import AppError
from jose import jwt
from jose.exceptions import JWTError
from datetime import datetime, timedelta, timezone


class JwtProvider:
    def __init__(self, secret_key: str = "secret_key", algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm

    def create_access_token(
        self, data: dict, expires_delta: timedelta = None or timedelta(minutes=15)
    ):
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + expires_delta
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret_key, self.algorithm)

    def decode_access_token(self, token: str):
        try:
            payload = jwt.decode(token, self.secret_key, self.algorithm)
            return payload
        except JWTError as e:
            raise AppError(f"Invalid token {e}", status_code=401)
