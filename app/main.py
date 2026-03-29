import json
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import engine
from app.models import Base
from app.routers import dashboard, documents, exceptions, alerts, chat, uploads, processed_documents, financial
from app.routers import vendor_po as vendor_po_router

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title="DMS Dashboard API",
    description="Document Management System API",
    version="1.0.0"
)

# Log full Pydantic validation errors so 422s are debuggable in the terminal
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    print(f"\n❌ 422 Validation Error on {request.method} {request.url}")
    print(f"   Raw body: {body.decode('utf-8', errors='replace')}")
    print(f"   Errors:   {json.dumps(exc.errors(), indent=2)}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


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
app.include_router(vendor_po_router.router)

@app.get("/")
async def root():
    return {"message": "DMS Dashboard API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
