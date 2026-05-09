# DMS Dashboard — Backend

FastAPI backend for the Document Management System (DMS). Handles automated PDF ingestion via AWS Textract, multi-strategy document linking, financial analytics, and an AI-powered chat assistant.

---

## Features

- **Document Ingestion** — Upload PDFs to AWS S3, trigger async Textract jobs, extract structured fields (amounts, dates, parties, line items)
- **Document Linking** — Auto-link invoices to POs and POs to contracts via multi-strategy matching (document number, amount, vendor name)
- **Financial Analytics** — Client PO / Vendor PO tracking, PO allocations, billing violation detection, margin summaries, and document lineage
- **Vendor PO Generator** — Create, update, and PDF-export vendor purchase orders
- **Alert System** — Auto-generated alerts for PO utilization thresholds, invoice-PO mismatches, and contract expiry
- **Exception Tracking** — Document validation exceptions with severity levels and assignment
- **Dashboard KPIs** — Utilization trends, category breakdowns, and summary statistics
- **Chat Assistant** — Rule-based responses with OpenAI GPT-3.5-turbo fallback
- **Background Relink** — APScheduler job re-links documents and advances statuses every minute

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI + Uvicorn (ASGI) |
| ORM / DB | SQLAlchemy + Alembic + PostgreSQL |
| PDF Processing | AWS S3 + AWS Textract (async) |
| AI / Chat | OpenAI GPT-3.5-turbo |
| Validation | Pydantic v2 |
| Scheduling | APScheduler (AsyncIOScheduler) |
| Config | pydantic-settings (.env) |

---

## Project Structure

```
app/
├── main.py                  # App setup, CORS, router registration, scheduler
├── config.py                # Settings via pydantic-settings
├── database.py              # Engine (PostgreSQL pool or SQLite fallback)
├── models.py                # SQLAlchemy models
├── schemas.py               # Pydantic schemas
├── routers/
│   ├── dashboard.py         # GET /api/dashboard
│   ├── documents.py         # CRUD + /msa-buckets
│   ├── uploads.py           # File upload, serve, delete, process
│   ├── processed_documents.py  # Read Textract JSON cache
│   ├── financial.py         # Client/Vendor POs, invoices, billing, margin
│   ├── vendor_po.py         # Vendor PO generator + PDF export
│   ├── exceptions.py        # Exception tracking
│   ├── alerts.py            # Alert CRUD
│   └── chat.py              # AI chat endpoint
└── services/
    ├── pdf_processor.py         # S3 upload → Textract → structured extraction
    ├── upload_service.py        # File save, duplicate detection, alert generation
    ├── document_service.py      # CRUD, MSA bucketing, KPIs, utilization trend
    ├── document_linking_service.py  # Invoice→PO→Contract linking
    ├── relink_service.py        # Scheduled re-link job
    ├── vendor_po_service.py     # Vendor PO creation + PDF generation
    ├── financial_service.py     # Financial aggregations
    ├── margin_service.py        # Margin calculations
    ├── billing_validation_service.py  # Billing violation detection
    ├── invoice_matching_service.py    # Invoice↔PO matching
    ├── alert_service.py         # Alert CRUD with priority ordering
    ├── alert_generator.py       # Alert rules engine
    └── chat_service.py          # Rule-based + OpenAI chat
```

---

## Installation

### 1. Create virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your values (see Configuration section below)
```

### 4. Run database migrations

```bash
alembic upgrade head
```

---

## Running the Application

**Development**
```bash
python start.py
# or
uvicorn app.main:app --reload --port 8000
```

**Production**
```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

API available at `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`  
ReDoc: `http://localhost:8000/redoc`

---

## Configuration

Create a `.env` file in the project root:

```env
# Database (PostgreSQL required for production)
DATABASE_URL=postgresql://user:password@localhost:5432/dmsdb

# Security
SECRET_KEY=your-secure-random-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OpenAI (for chat assistant)
OPENAI_API_KEY=sk-...

# AWS (for PDF processing via Textract)
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=us-east-1
AWS_S3_BUCKET=your-s3-bucket-name
KB_S3_BUCKET=your-knowledge-base-bucket-name

# File Upload
UPLOAD_DIR=./uploads
MAX_FILE_SIZE=10485760  # 10 MB

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

> **Note:** Never commit real credentials to version control. Rotate any keys that have been exposed.

---

## API Endpoints

### Dashboard
| Method | Path | Description |
|---|---|---|
| GET | `/api/dashboard` | KPIs, utilization trends, category breakdown |

### Documents
| Method | Path | Description |
|---|---|---|
| GET | `/api/documents` | List all documents |
| GET | `/api/documents/{id}` | Document detail with exceptions/alerts |
| POST | `/api/documents` | Create document |
| PUT | `/api/documents/{id}` | Update document |
| DELETE | `/api/documents/{id}` | Delete document |
| GET | `/api/documents/msa-buckets` | MSA bucket summary |

### File Uploads
| Method | Path | Description |
|---|---|---|
| POST | `/api/uploads` | Upload PDF/file |
| GET | `/api/uploads/{filename}` | Download file |
| DELETE | `/api/uploads/{filename}` | Delete file |
| POST | `/api/uploads/process/{filename}` | Trigger Textract processing |

### Processed Documents
| Method | Path | Description |
|---|---|---|
| GET | `/api/processed-documents` | List Textract-processed JSON results |
| GET | `/api/processed-documents/{id}` | Get single processed document |

### Financial
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/financial/client-pos` | Client purchase orders |
| GET/POST | `/api/financial/vendor-pos` | Vendor purchase orders |
| GET/POST | `/api/financial/po-allocations` | PO allocations (Layer 2) |
| GET/POST | `/api/financial/vendor-invoices` | Vendor invoices |
| GET/POST | `/api/financial/client-invoices` | Client invoices |
| GET | `/api/financial/billing-violations` | Billing violation report |
| GET | `/api/financial/margin-summary` | Margin summary |
| GET | `/api/financial/lineage/{document_id}` | Document lineage trace |

### Vendor PO Generator
| Method | Path | Description |
|---|---|---|
| POST | `/api/vendor-po/generate` | Create PO and generate PDF |
| GET | `/api/vendor-po` | List all generated POs |
| GET | `/api/vendor-po/{po_id}` | Get single PO |
| PUT | `/api/vendor-po/{po_id}` | Update PO and re-generate PDF |
| DELETE | `/api/vendor-po/{po_id}` | Delete PO and its PDF |
| POST | `/api/vendor-po/{po_id}/regenerate-pdf` | Force PDF regeneration |

### Exceptions
| Method | Path | Description |
|---|---|---|
| GET | `/api/exceptions` | List exceptions |
| GET | `/api/exceptions/{id}` | Get exception |
| POST | `/api/exceptions` | Create exception |
| PUT | `/api/exceptions/{id}` | Update exception |
| DELETE | `/api/exceptions/{id}` | Delete exception |

### Alerts
| Method | Path | Description |
|---|---|---|
| GET | `/api/alerts` | List alerts (priority ordered) |
| GET | `/api/alerts/{id}` | Get alert |
| POST | `/api/alerts` | Create alert |
| PUT | `/api/alerts/{id}` | Update alert |
| DELETE | `/api/alerts/{id}` | Delete alert |

### Chat
| Method | Path | Description |
|---|---|---|
| POST | `/api/chat` | Send message to AI assistant |

---

## Database Migrations

The project uses Alembic for schema migrations.

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "describe your change"

# Rollback one step
alembic downgrade -1
```

---

## Frontend Integration

The backend is designed to work with the companion Next.js frontend. Set the API base URL in the frontend's `.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## Production Deployment

1. Use PostgreSQL — set `DATABASE_URL` accordingly
2. Run migrations: `alembic upgrade head`
3. Use Gunicorn with Uvicorn workers:
   ```bash
   gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
   ```
4. Set up a reverse proxy (Nginx) in front of Gunicorn
5. Ensure AWS IAM credentials have S3 read/write and Textract permissions
6. Store all secrets in environment variables or a secrets manager — never in source control
