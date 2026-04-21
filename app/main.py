import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.database import engine, SessionLocal
from app.models import Base
from app.routers import dashboard, documents, exceptions, alerts, chat, uploads, processed_documents, financial
from app.routers import vendor_po as vendor_po_router

# Create database tables
Base.metadata.create_all(bind=engine)

# Make client_pos.document_id nullable for manually-created clients
try:
    with engine.connect() as _conn:
        _conn.execute(__import__("sqlalchemy").text(
            "ALTER TABLE client_pos ALTER COLUMN document_id DROP NOT NULL"
        ))
        _conn.commit()
except Exception:
    pass  # already nullable or SQLite (which ignores NOT NULL alterations)


async def _run_relink():
    """Scheduled job: re-link documents and advance statuses every 1 minute."""
    db = SessionLocal()
    try:
        from app.services.relink_service import RelinkService
        stats = RelinkService(db).run_full_relink()
        print(f"[scheduler] relink completed: {stats}")
    except Exception as exc:
        import traceback
        print(f"[scheduler] relink failed: {exc}")
        print(traceback.format_exc())
        db.rollback()
    finally:
        db.close()


scheduler = AsyncIOScheduler()
scheduler.add_job(_run_relink, "interval", minutes=1, id="relink_job")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔧 AWS Configuration Check:")
    print(f"   AWS_ACCESS_KEY_ID set: {bool(settings.aws_access_key_id)}")
    print(f"   AWS_SECRET_ACCESS_KEY set: {bool(settings.aws_secret_access_key)}")
    print(f"   AWS_REGION: {settings.aws_region}")
    print(f"   AWS_S3_BUCKET: {settings.aws_s3_bucket or '⚠️  not set'}")
    print(f"   AWS_S3_KB_BUCKET: {settings.kb_s3_bucket or '⚠️  not set'}")
    scheduler.start()
    print("[scheduler] relink job started — runs every 1 minute")
    yield
    scheduler.shutdown(wait=False)
    print("[scheduler] stopped")


# Create FastAPI app
app = FastAPI(
    title="DMS Dashboard API",
    description="Document Management System API",
    version="1.0.0",
    lifespan=lifespan,
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
