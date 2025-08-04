from core.util.db_session import db_dependency
from core.util.app_error import AppError
from users.services.auth_service import LoginResponse
from fastapi.exceptions import HTTPException
from fastapi.routing import APIRouter
from users.models.dto.create_user_dto import CreateUserDto
from users.models.dto.login_dto import LoginDto
from users.services.auth_service import AuthService
from users.services.user_service import UserService

users_router: APIRouter = APIRouter(
    prefix="/users",
    tags=["users"],
)


@users_router.post("/register")
async def register_user(user: CreateUserDto, db: db_dependency):
    user_service: UserService = UserService(db)
    try:
        user = user_service.create_user(user)
        print(f"User created: {user}")
        return {"message": "User registered successfully"}
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@users_router.post("/login", response_model=LoginResponse)
async def login_user(data: LoginDto, db: db_dependency):
    auth_service = AuthService(db)

    try:
        return auth_service.login(data)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
