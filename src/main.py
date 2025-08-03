from sqlalchemy.orm import Mapped, mapped_column
from core.util.db_session import engine
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from pydantic import BaseModel, Field
import shutil
from users.router import users_router
from core.util.db_session import Base, db_dependency


# --- models.py ---
class DBFile(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name = Column(String, index=True)
    path = Column(String, unique=True, index=True)  # Full path on the server
    size = Column(Integer)
    upload_date = Column(DateTime, default=datetime.utcnow)
    is_directory = Column(Boolean, default=False)


# --- schemas.py ---
class FileBase(BaseModel):
    name: str
    is_directory: bool = False


class FileCreate(FileBase):
    pass


class FileData(FileBase):
    id: uuid.UUID
    path: str
    size: Optional[int] = None
    upload_date: datetime

    class Config:
        from_attributes = True


class DirectoryCreate(BaseModel):
    name: str
    parent_path: str = ""  # Relative path from UPLOAD_DIRECTORY


class DirectoryRename(BaseModel):
    new_name: str = Field(min_length=1, description="The new name for the directory.")


# --- crud.py ---
def create_db_file(db: db_dependency, file: FileCreate, file_path: str, file_size: int):
    db_file = DBFile(
        name=file.name, path=file_path, size=file_size, is_directory=file.is_directory
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file


def get_db_file_by_path(db: db_dependency, file_path: str):
    return db.query(DBFile).filter(DBFile.path == file_path).first()


# Casting text to UUID => uuid.UUID(file_id)
def get_db_file_by_id(db: db_dependency, file_id: uuid.UUID):
    return db.query(DBFile).filter(DBFile.id == file_id).first()


def get_db_files(db: db_dependency, skip: int = 0, limit: int = 100):
    return db.query(DBFile).offset(skip).limit(limit).all()


def delete_db_file(db: db_dependency, file_id: uuid.UUID):
    db_file = db.query(DBFile).filter(DBFile.id == file_id).first()
    if db_file:
        db.delete(db_file)
        db.commit()
    return db_file


def update_db_file_path_and_name(
    db: db_dependency, db_file: DBFile, new_path: str, new_name: str
):
    db_file.path = new_path
    db_file.name = new_name
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file


# --- main.py (continued) ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
        # "http://localhost:3000",
    ],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Define the directory where uploaded files will be stored
UPLOAD_DIRECTORY = "static"

# Create the upload directory if it doesn't exist
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)


# Create database tables on startup
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/uploadfile/", response_model=FileData)
async def upload_file(file: UploadFile, db: db_dependency):
    """
    Uploads a file to the server and stores its metadata in the database.
    """
    file_location = os.path.join(UPLOAD_DIRECTORY, file.filename)

    # Check if a file with the same name already exists in the database
    existing_file = get_db_file_by_path(db, file_location)
    if existing_file:
        raise HTTPException(
            status_code=400, detail="File with this name already exists."
        )

    try:
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save file: {e}")

    file_size = os.path.getsize(file_location)
    file_create = FileCreate(name=file.filename, is_directory=False)
    db_file = create_db_file(db, file_create, file_location, file_size)
    return db_file


@app.post("/create_directory/", response_model=FileData)
async def create_directory(directory_data: DirectoryCreate, db: db_dependency):
    """
    Creates a new directory on the server and stores its metadata in the database.
    """
    # Construct the full path for the new directory
    full_path = os.path.join(
        UPLOAD_DIRECTORY, directory_data.parent_path, directory_data.name
    )
    full_path = os.path.normpath(full_path)  # Normalize path to handle ".." etc.

    # Ensure the path is within the UPLOAD_DIRECTORY
    if not full_path.startswith(os.path.abspath(UPLOAD_DIRECTORY)):
        raise HTTPException(status_code=400, detail="Invalid directory path.")

    # Check if a directory or file with the same name already exists
    if os.path.exists(full_path):
        raise HTTPException(
            status_code=400, detail="A file or directory with this name already exists."
        )

    existing_db_entry = get_db_file_by_path(db, full_path)
    if existing_db_entry:
        raise HTTPException(
            status_code=400, detail="A database entry for this path already exists."
        )

    try:
        os.makedirs(full_path, exist_ok=False)  # exist_ok=False to prevent overwriting
    except FileExistsError:
        raise HTTPException(status_code=400, detail="Directory already exists.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not create directory: {e}")

    directory_create = FileCreate(name=directory_data.name, is_directory=True)
    db_directory = create_db_file(
        db, directory_create, full_path, 0
    )  # Size for directory is 0
    return db_directory


@app.put("/directories/{directory_id}/rename", response_model=FileData)
async def rename_directory(
    directory_id: uuid.UUID, rename_data: DirectoryRename, db: db_dependency
):
    """
    Renames an existing directory.
    """
    db_directory = get_db_file_by_id(db, directory_id)

    if not db_directory:
        raise HTTPException(status_code=404, detail="Directory not found.")
    if not db_directory.is_directory:
        raise HTTPException(
            status_code=400, detail="The specified ID does not belong to a directory."
        )

    old_path = db_directory.path
    # Ensure the old path is within the UPLOAD_DIRECTORY
    if not os.path.abspath(old_path).startswith(os.path.abspath(UPLOAD_DIRECTORY)):
        raise HTTPException(
            status_code=400, detail="Invalid directory path for renaming."
        )

    # Construct the new path
    parent_dir = os.path.dirname(old_path)
    new_path = os.path.join(parent_dir, rename_data.new_name)
    new_path = os.path.normpath(new_path)

    # Prevent path traversal
    if not new_path.startswith(os.path.abspath(UPLOAD_DIRECTORY)):
        raise HTTPException(
            status_code=400,
            detail="Invalid new directory name or path traversal attempt.",
        )

    # Check if the new path already exists on the file system
    if os.path.exists(new_path):
        raise HTTPException(
            status_code=400,
            detail="A file or directory with the new name already exists.",
        )

    # Check if a database entry for the new path already exists
    existing_db_entry = get_db_file_by_path(db, new_path)
    if existing_db_entry:
        raise HTTPException(
            status_code=400, detail="A database entry for the new path already exists."
        )

    try:
        # Rename on file system
        os.rename(old_path, new_path)
    except OSError as e:
        raise HTTPException(
            status_code=500, detail=f"Could not rename directory on file system: {e}"
        )

    # Update in database
    updated_directory = update_db_file_path_and_name(
        db, db_directory, new_path, rename_data.new_name
    )

    # IMPORTANT: If renaming a directory, all its children's paths in the DB also need to be updated.
    # This is a more complex operation and is not implemented in this basic CRUD.
    # For a full-featured file explorer, you would need to:
    # 1. Find all files/directories in the database whose paths start with `old_path`.
    # 2. Update their paths to reflect the new parent path (`new_path`).
    # This would typically involve a recursive update or a more sophisticated path management strategy.
    # For this basic example, we are only updating the parent directory's path.

    return updated_directory


@app.get("/files/", response_model=List[FileData])
def list_files(db: db_dependency):
    """
    Lists all files and directories stored in the database.
    """
    files = get_db_files(db)
    return files


@app.get("/files/{file_id}/download")
async def download_file(file_id: uuid.UUID, db: db_dependency):
    """
    Downloads a file by its ID.
    """
    db_file = get_db_file_by_id(db, file_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    if db_file.is_directory:
        raise HTTPException(status_code=400, detail="Cannot download a directory.")

    file_path = db_file.path
    if not os.path.exists(file_path):
        # If file exists in DB but not on disk, remove from DB
        delete_db_file(db, file_id)
        raise HTTPException(
            status_code=404, detail="File not found on disk. Database entry removed."
        )

    # Ensure the file being downloaded is within the UPLOAD_DIRECTORY
    if not os.path.abspath(file_path).startswith(os.path.abspath(UPLOAD_DIRECTORY)):
        raise HTTPException(status_code=400, detail="Invalid file path for download.")

    return FileResponse(
        path=file_path, filename=db_file.name, media_type="application/octet-stream"
    )


@app.delete("/files/{file_id}", response_model=FileData)
def delete_file(file_id: uuid.UUID, db: db_dependency):
    """
    Deletes a file or directory by its ID from both the database and the file system.
    """
    db_file = get_db_file_by_id(db, file_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="File or directory not found")

    file_path = db_file.path

    # Ensure the path being deleted is within the UPLOAD_DIRECTORY
    if not os.path.abspath(file_path).startswith(os.path.abspath(UPLOAD_DIRECTORY)):
        raise HTTPException(status_code=400, detail="Invalid path for deletion.")

    # Delete from file system
    if os.path.exists(file_path):
        try:
            if db_file.is_directory:
                shutil.rmtree(file_path)  # Remove directory and its contents
            else:
                os.remove(file_path)  # Remove file
        except OSError as e:
            raise HTTPException(
                status_code=500, detail=f"Could not delete from file system: {e}"
            )
    else:
        print(
            f"Warning: File system entry not found for {file_path}, but database entry exists. Deleting database entry."
        )

    # Delete from database
    deleted_file = delete_db_file(db, file_id)
    if not deleted_file:
        raise HTTPException(status_code=500, detail="Failed to delete database entry.")

    return deleted_file


app.include_router(users_router, prefix="/api")
