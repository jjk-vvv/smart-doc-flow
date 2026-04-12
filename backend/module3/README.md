# module3

`module3` is the backend service for multi-source data fusion. It supports:

- template upload: `.xlsx`, `.docx`
- source upload: `.docx`, `.xlsx`, `.txt`, `.md`
- task execution and status polling
- result preview and download
- Excel / Word structured write-back APIs

## 1. Install

Use Python 3.11+.

```bash
cd backend/module3
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Environment variables

Copy `.env.example` to `.env` and fill in your real values.

Required:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_API_MODE`

Optional:

- `MODULE3_DATABASE_URL`
- `OPENAI_MAX_IMAGES`
- `OPENAI_MAX_IMAGE_BYTES`
- `PREVIEW_LINE_LIMIT`
- `PREVIEW_CHAR_LIMIT`

## 3. Database setup

`module3` supports PostgreSQL, but database is optional.

If you want to enable PostgreSQL:

1. Create a database, for example `module3`
2. Set `MODULE3_DATABASE_URL` in `.env`
3. Make sure the PostgreSQL user/password/port in `.env` match your local database

Example:

```env
MODULE3_DATABASE_URL=postgresql+psycopg://postgres:your_password@localhost:5433/module3
```

If `MODULE3_DATABASE_URL` is left empty, the service will run without database persistence and will use local storage files under `backend/module3/storage`.

## 4. Start the service

From the project root:

```bash
uvicorn backend.module3.main:app --reload --host 0.0.0.0 --port 8001
```

Or from `backend/module3`:

```bash
python main.py
```

## 5. Storage directories

Runtime files are stored under:

- `storage/templates`
- `storage/docsets`
- `storage/runs`
- `storage/tmp_docx_images`

These directories are runtime data, not source code. They usually should not be committed to a remote repository.
