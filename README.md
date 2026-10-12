# AI Dashboard Agent — local MVP

Ứng dụng local gồm Next.js App Router ở cổng 3000 và FastAPI ở cổng 8000. Hiện đã có scaffold, health check và migration metadata dự thảo; health không kết nối database, còn authentication, dashboard API và LLM chưa được triển khai.

## Yêu cầu

- Windows PowerShell 5.1+ hoặc PowerShell 7.
- Python 3.11 (project chấp nhận `>=3.11,<3.13`).
- Node.js `>=20.9.0`; đã kiểm tra với Node 22.
- PostgreSQL chưa cần để chạy health check P1-T01.
- Không cần LLM API key.

## Thiết lập lần đầu

Chạy từ thư mục repository:

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local

.\.venv\Scripts\python.exe -m pip install --requirement backend/requirements.lock

Push-Location frontend
npm ci
Pop-Location
```

Không commit `backend/.env`, `frontend/.env.local`, `.venv`, backup hoặc log. Các dependency Python và npm đã được pin trong lockfile; dùng `npm ci`, không dùng install không khóa phiên bản trong quy trình tái lập.

## Chạy local

```powershell
.\scripts\start-local.ps1
```

Script kiểm tra config/dependency, chạy FastAPI ẩn ở `127.0.0.1:8000`, chờ health thành công rồi chạy Next.js ở `127.0.0.1:3000`. Nhấn `Ctrl+C` để dừng frontend; script sẽ dừng backend do chính nó tạo.

Mở:

- UI: <http://localhost:3000>
- Health trực tiếp: <http://localhost:8000/api/health>
- Health cùng origin qua Next.js: <http://localhost:3000/api/health>

`/api/:path*` được Next.js chuyển tiếp nguyên đường dẫn đến `BACKEND_URL`. Browser không gọi trực tiếp cổng 8000.

## Chạy từng service

Backend:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
Pop-Location
```

Frontend:

```powershell
Push-Location frontend
npm run dev
Pop-Location
```

## Kiểm tra P1-T01

```powershell
$env:APP_ENV = 'test'
.\.venv\Scripts\python.exe -c "from fastapi.testclient import TestClient; from backend.app.main import app; r=TestClient(app).get('/api/health'); assert r.status_code == 200; print(r.json())"
Remove-Item Env:APP_ENV

Push-Location frontend
$env:BACKEND_URL = 'http://127.0.0.1:8000'
npm run lint
npm run typecheck
npm run build
Remove-Item Env:BACKEND_URL
Pop-Location
```

Kiểm tra lỗi config rõ ràng:

- Thiếu `APP_ENV` và không có `backend/.env`: backend dừng với validation error chỉ rõ field `app_env` bị thiếu.
- Thiếu `BACKEND_URL` và không có `frontend/.env.local`: Next.js dừng với thông báo hướng dẫn copy `.env.example`.

## Dữ liệu và bằng chứng

- Import nguồn: `data/real-estate-sales-sample-database-v3-sql-postgres.sql` — không tự động import hoặc sửa.
- Audit và từ điển: `docs/data-audit.md`, `docs/data-dictionary.md`.
- KPI/golden fixtures: `docs/kpi-catalog.md`, `backend/tests/fixtures/`.
- Bộ 30 câu đánh giá và report template: `backend/tests/evaluation/prompts.json`, `docs/acceptance-report.md`.

Live database audit vẫn bị chặn cho tới khi có credential chỉ đọc. Không coi baseline file import là bằng chứng DB thật.

## Migration metadata P1-T02

Hai tài khoản PostgreSQL phải tách biệt:

- `MIGRATION_DATABASE_URL`: role migration sở hữu/thay đổi schema `app` và `analytics`; không dùng trong API.
- `RUNTIME_DATABASE_URL`: role runtime phục vụ ứng dụng; không là owner/superuser/BYPASSRLS và không có quyền DDL.

Health check không cần hai biến này. Trước mọi Alembic upgrade, tạo backup custom-format:

```powershell
$env:MIGRATION_DATABASE_URL = '<postgresql-url-cua-role-migration>'
.\scripts\backup-db.ps1
```

Script không in URL, chuyển credential sang biến môi trường libpq thay vì command line, chạy `pg_restore --list` để xác nhận archive đọc được và ghi SHA-256. Phải restore archive vào database test tách biệt, chạy cycle `upgrade → downgrade → upgrade`, đối chiếu 16 bảng nguồn, rồi mới đặt gate trong đúng process migration:

Script chấp nhận scheme `postgres://`, `postgresql://` và `postgresql+psycopg://`. URL có query parameter hoặc fragment bị từ chối rõ ràng để không âm thầm bỏ qua tùy chọn kết nối; đặt tùy chọn libpq cần thiết (ví dụ `PGSSLMODE`) bằng biến môi trường process trước khi chạy script.

```powershell
$env:MIGRATION_BACKUP_VERIFIED = 'true'
Push-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

Không đặt `MIGRATION_BACKUP_VERIFIED=true` lâu dài trong file config. Migration `0001_app_schema` chỉ tạo `app`, `analytics`, chín bảng metadata trong `app` và bảng quản lý version của Alembic; không import, update, truncate hoặc drop bảng nguồn `public`.

Integration test chỉ chấp nhận database có chữ `test` trong tên và một bản backup đã restore rõ ràng:

```powershell
$env:MIGRATION_TEST_DATABASE_URL = '<postgresql-url-db-test-da-restore>'
$env:MIGRATION_TEST_BACKUP_RESTORED = 'true'
$env:RUNTIME_TEST_DATABASE_URL = '<postgresql-url-role-runtime-tren-db-test>'
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_migrations.py -q
```

Khi thiếu các credential test này, integration migration/privilege là `BLOCKED`; test skip không được tính là đạt.

Thiết lập ba reader scope, membership role và kiểm thử RLS được mô tả trong [docs/local-runbook.md](docs/local-runbook.md). Reader credentials không dùng thay runtime/migration credential và không có scope mặc định.

## Auth local và tài khoản demo P1-T04

Auth dùng cookie session opaque; database chỉ lưu SHA-256 của token. Cookie là `HttpOnly`, `SameSite=Lax` và bật `Secure` trong production. `POST /api/auth/login` và `POST /api/auth/logout` chỉ chấp nhận header `Origin` khớp `FRONTEND_ORIGIN`; role và scope luôn được đọc lại từ `app.users`, không nhận từ request.

Seed yêu cầu bốn mật khẩu qua environment hoặc `backend/.env` và không có mật khẩu mặc định:

```powershell
$env:SEED_BUILDER_ALL_PASSWORD = '<secret-at-least-12-characters>'
$env:SEED_VIEWER_ALL_PASSWORD = '<secret-at-least-12-characters>'
$env:SEED_VIEWER_CA_PASSWORD = '<secret-at-least-12-characters>'
$env:SEED_BUILDER_TX_PASSWORD = '<secret-at-least-12-characters>'
.\.venv\Scripts\python.exe backend\scripts\seed_users.py
```

Script có thể chạy lặp lại mà không tạo username trùng. Không ghi các giá trị này vào source, log hoặc commit. Integration auth chỉ chạy trên database test riêng:

```powershell
$env:AUTH_TEST_DATABASE_URL = '<runtime-role-url-on-test-db>'
.\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_auth.py -q
```

