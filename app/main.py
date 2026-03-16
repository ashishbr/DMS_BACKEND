from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import engine
from app.models import Base
from app.routers import dashboard, documents, exceptions, alerts, chat, uploads, processed_documents, financial

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title="DMS Dashboard API",
    description="Document Management System API",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for uploads
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# Include routers
app.include_router(dashboard.router)
app.include_router(documents.router)
app.include_router(exceptions.router)
app.include_router(alerts.router)
app.include_router(chat.router)
app.include_router(uploads.router)
app.include_router(processed_documents.router)
app.include_router(financial.router)

@app.get("/")
async def root():
    return {"message": "DMS Dashboard API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
