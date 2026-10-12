# IMPLEMENTATION PLAN — AI Agent tạo Dashboard bất động sản

Ngày tổng hợp: 12/10/2026. Nguồn: bản “Kế hoạch MVP local” đã thống nhất và được người dùng đính kèm.

**Trạng thái: chỉ lập tài liệu, chưa triển khai code.** Mọi checkbox dưới đây là công việc tương lai. Đường dẫn file là cấu trúc triển khai dự kiến, không có nghĩa file đã tồn tại. Tài liệu này không xác nhận database đang chạy đã được đối soát.

## 1. Mục tiêu, phạm vi và các quyết định đã chốt

Xây ứng dụng local để lãnh đạo doanh nghiệp bất động sản tạo dashboard từ yêu cầu tiếng Việt, chỉnh sửa bằng hội thoại và duyệt trước khi lưu chính thức.

- Builder: tạo, chỉnh sửa, xem SQL/định nghĩa KPI và duyệt dashboard mình sở hữu.
- Viewer: xem dashboard đã duyệt, đổi bộ lọc và tải lại dữ liệu; không gọi Agent hoặc duyệt lưu.
- Một doanh nghiệp/workspace; dashboard đã duyệt chia sẻ trong workspace, nhưng dữ liệu tính theo quyền người đang xem.
- Phân quyền theo `properties.state`, với ba profile ban đầu `ALL`, `CA`, `TX`.
- LLM tạo `AnalysisPlan` có cấu trúc; backend biên dịch SQL từ KPI catalog đã kiểm chứng. Không thực thi SQL tùy ý do LLM hoặc client gửi.
- Làm luồng end-to-end không cần API LLM trước; sau đó tích hợp một provider qua adapter nhỏ.
- Chỉ local, chưa triển khai Vercel/Cloud Run. API LLM vẫn là dịch vụ bên ngoài nếu bật chế độ thật.
- Chưa làm multi-tenant, nhiều cấp duyệt, kéo-thả layout, dự báo, xuất PDF, lịch gửi báo cáo, KPI lợi nhuận/hoa hồng/chỉ tiêu hay phân tích theo đại lý.
- Không thêm Redis, Celery, vector database, nhiều agent hoặc cache kết quả dùng chung trong MVP.

### 1.1. Hiện trạng và giới hạn bằng chứng

- Workspace: `D:/AI-Dashboard-Agent`; `frontend/` và `backend/` trống tại thời điểm khảo sát, chưa có Git repository.
- File nguồn hiện có: `data/real-estate-sales-sample-database-v3-sql-postgres.sql`.
- Theo khảo sát trước: PostgreSQL đang chạy trên `localhost:5432`; kết nối cần mật khẩu. Phiên bản 16.9 và database `real_estate_db` là thông tin người dùng cung cấp, cần xác minh bằng kết nối thật ở P0-T01.
- File import có 16 bảng, 16 khóa chính và 16 khóa ngoại; dữ liệu tổng hợp dùng thử nghiệm.
- Không import lại, chỉnh dữ liệu nguồn hoặc áp dụng migration lên DB hiện có trong bước tạo tài liệu này.

| Nhóm | Bảng và số dòng trong file import |
|---|---|
| Giao dịch | `transactions`: 1.000 |
| Bất động sản | `properties`: 125; `property_types`: 8 |
| Môi giới/đại lý | `agents`: 125; `agencies`: 16; `agent_agencies`: 125 |
| Khách hàng/chào giá | `clients`: 125; `offers`: 125 |
| Định giá/kiểm định/sửa chữa | `appraisals`, `inspections`, `repairs`: mỗi bảng 125 |
| Danh mục | `appraisers`: 16; `inspectors`: 16; `payment_methods`: 6 |
| Khu dân cư | `neighbourhoods`: 16; `property_neighbourhoods`: 125 |

Giao dịch trong file trải từ 12/02/2021 đến 13/07/2026. Có 125 bất động sản khác nhau có giao dịch; một bất động sản có thể có nhiều giao dịch. Gán giao dịch vào đại lý bằng lịch sử làm việc của môi giới cho kết quả 631 giao dịch không khớp đại lý, 200 giao dịch khớp nhiều đại lý. Vì vậy chưa dùng phép JOIN này cho KPI. Quan hệ bất động sản–khu dân cư cũng có nguy cơ nhân bản số liệu; MVP dùng `properties.state` và `properties.city`.

### 1.2. Mốc đối soát

Các giá trị sau chỉ là baseline từ file import, áp dụng toàn bộ thời gian. Nếu DB thật khác file, phải báo cáo khác biệt và xác lập baseline DB, không chỉnh dữ liệu để ép khớp.

| Phạm vi | Số giao dịch | Tổng `sale_price` |
|---|---:|---:|
| ALL | 1.000 | 870.798.679,64 |
| CA | 135 | 107.064.313,73 |
| TX | 132 | 128.635.636,80 |

## 2. Tech stack và kiến trúc hệ thống

| Lớp | Công nghệ/quyết định |
|---|---|
| Frontend | Next.js App Router, React, TypeScript, ECharts, CSS Grid |
| Backend | FastAPI, Pydantic, SQLAlchemy, psycopg |
| Agent | LangGraph, structured output, một LLM adapter và mock adapter |
| Database | PostgreSQL 16.9 theo môi trường dự kiến; xác minh phiên bản ở phase 0 |
| Migration | Alembic; tài khoản migration tách tài khoản runtime |
| Auth | Argon2, server-side session, cookie HttpOnly/SameSite |
| Kiểm tra SQL | AST parser hỗ trợ PostgreSQL; chọn SQLGlot khi triển khai, kiểm thử với SQL compiler |
| Kiểm thử | pytest, HTTPX/FastAPI test client, test integration PostgreSQL, Playwright |
| Local runtime | Next.js cổng 3000, FastAPI cổng 8000, PostgreSQL cổng 5432; một backend process |
| Dependency | Chốt phiên bản tương thích và commit lockfile khi scaffold; không dùng version trôi nổi |

```text
Browser
  │ cookie phiên, request cùng origin
  ▼
Next.js :3000 — trang đăng nhập, dashboard, hội thoại, ECharts
  │ chuyển tiếp /api
  ▼
FastAPI :8000 — auth, RBAC, ownership, scope, dashboard APIs
  ├── LangGraph → LLM adapter → LLM API hoặc mock
  │       ↓
  │   AnalysisPlan → semantic validation → KPI catalog
  │       ↓
  │   SQL compiler → AST validation → EXPLAIN → read-only execution
  │       ↓
  │   QueryResult + DashboardSpec → preview → HITL
  │
  └── PostgreSQL / real_estate_db
          ├── public: 16 bảng nguồn
          ├── analytics: view security_invoker
          └── app: users, sessions, dashboard versions,
                   conversations, checkpoints, usage, audit
```

### 2.1. Ranh giới quyền và dữ liệu

1. Backend xác thực phiên và đọc vai trò/profile từ dữ liệu server; không tin profile, user ID hoặc thread ID do prompt tự chỉ định.
2. Dùng ba reader role/kết nối tương ứng `ALL/CA/TX`; không dùng credential ghi metadata để chạy SQL phân tích.
3. RLS trên `properties`, `transactions`, `offers`, `repairs`; fact chỉ nhìn thấy bất động sản thuộc phạm vi được cấp.
4. Reader role không là owner/superuser/BYPASSRLS và không được chuyển sang role phạm vi khác.
5. View `security_invoker` dùng quyền của caller; cấp tối thiểu quyền cột nguồn cần thiết để view hoạt động. Không cấp email, điện thoại hoặc thông tin cá nhân khách hàng cho lớp analytics.
6. Mở dashboard luôn thực thi lại theo người xem, giao bộ lọc với scope. Giao rỗng trả trạng thái không có dữ liệu; không mở rộng phạm vi ngầm.
7. Mọi endpoint conversation/draft/approval kiểm tra Builder và ownership; dashboard public trong workspace chỉ gồm phiên bản đã duyệt.
8. Seed bốn tài khoản: Builder ALL, Viewer ALL, Viewer CA, Builder TX. Mật khẩu không hardcode trong source hoặc log.

### 2.2. KPI catalog và độ chính xác

| KPI ID dự kiến | Định nghĩa | Grain/thời gian | Phase |
|---|---|---|---|
| `sales_value` | SUM(sale_price) | transaction / transaction_date | 2 |
| `transaction_count` | COUNT(transaction_id) | transaction / transaction_date | 2 |
| `average_sale_value` | SUM(sale_price) / COUNT(transaction_id) | transaction / transaction_date | 2 |
| `sold_property_count` | COUNT(DISTINCT property_id) | property trong tập giao dịch lọc | 2 |
| `offer_count` | COUNT(offer_id) | offer / offer_date | 4 |
| `accepted_offer_rate` | accepted offers / all offers trong kỳ | offer / offer_date | 4 |
| `repair_cost` | SUM(cost) | repair / repair_date | 4 |

- Catalog có version, mô tả tiếng Việt, nguồn, công thức, đơn vị, grain, trường ngày và chiều phân tích hợp lệ.
- Giao dịch hỗ trợ thời gian, bang, thành phố, loại bất động sản, môi giới. Offers/repairs không nhận dimension môi giới khi không có quan hệ hợp lệ.
- Mỗi query chỉ có một fact; không JOIN nhiều fact rồi SUM. DISTINCT và tỷ lệ phải tính lại cho tập dữ liệu được lọc.
- Dùng NUMERIC/Decimal; chỉ làm tròn khi hiển thị. Hợp đồng JSON phải giữ được độ chính xác tiền.
- Tên KPI là “giá trị giao dịch”, không phải doanh thu hoa hồng. Tỷ lệ accepted offer không phải tỷ lệ chốt giao dịch.
- Đơn vị tiền: “đơn vị tiền của dataset” cho đến khi có xác nhận, không tự gán USD.
- Ngày tương đối tính theo Asia/Ho_Chi_Minh tại thời điểm request; không cố định vào ngày viết kế hoạch. Không nêu thời gian thì dùng toàn bộ khoảng dữ liệu, ghi rõ trên UI.
- Không có mẫu số hoặc mẫu số bằng 0: trả trạng thái không đủ cơ sở; không chia cho 0. Nếu hỗ trợ so sánh kỳ, áp dụng cùng nguyên tắc, không tự bổ sung KPI ngoài catalog.

### 2.3. Agent, phiên bản và HITL

```text
Yêu cầu → auth/scope → tải ngữ cảnh và catalog → structured AnalysisPlan
→ kiểm tra ngữ nghĩa → compiler/validator → query → dựng preview
→ awaiting_approval → duyệt đúng draft → phiên bản chính thức
```

- Phân biệt cần làm rõ, không hỗ trợ, lỗi thực thi và preview thành công; không bịa KPI để hoàn thành yêu cầu.
- Hỗ trợ card, line, bar, horizontal bar, pie/donut, table. Mặc định tổng quan: ba card + ba chart; tối đa tám widget và sáu query khác nhau.
- Render từ cấu trúc đã kiểm tra; không eval JavaScript, HTML hoặc formatter do LLM gửi.
- Draft/checkpoint được lưu nội bộ để phục hồi; đây không phải phát hành dashboard. Viewer không thấy draft.
- Chỉnh sửa dashboard đã lưu tạo draft mới; giữ bản đã duyệt phục vụ Viewer.
- Approval gắn draft revision/hash và base dashboard version; draft cũ trả 409, approval lặp trả cùng kết quả, không tạo version mới.
- Mỗi hội thoại một lượt chạy; cập nhật có kiểm soát đồng thời. Không giữ transaction DB mở trong lúc chờ LLM hoặc chờ người duyệt.
- LangGraph dùng PostgreSQL checkpointer, thread ID server quản lý và interrupt. Thiết kế node sau resume để không lặp side effect.
- Thay đổi chỉ cách trình bày tái sử dụng kết quả draft khi query/filter/scope còn nguyên; không dùng cache chung giữa người dùng.

### 2.4. Giới hạn tài nguyên và xử lý lỗi

| Hạng mục | Giá trị/điều kiện mặc định |
|---|---|
| SQL | SELECT do compiler tạo; tham số hóa filter; allowlist view/cột/hàm/cấu trúc |
| Thực thi | Transaction read-only; statement_timeout 5 giây/query |
| Kết quả | Tối đa 1.000 dòng/query; báo cần giảm độ chi tiết khi vượt, không âm thầm cắt chuỗi thời gian |
| Chi phí DB | EXPLAIN FORMAT JSON; hiệu chỉnh ngưỡng trên query hợp lệ, không coi planner cost là tiền/thời gian |
| LLM calls | Tối đa ba calls/lượt, bao gồm retry; tối đa một vòng sửa structured output |
| Token/thời gian | Tổng tối đa 24.000 token/lượt; 60 giây/lượt LLM |
| Ngân sách | 0,10 USD/lượt; 1 USD/ngày/Builder; cấu hình được |
| Provider thật | Cần endpoint, model, key và bảng giá trước khi bật |
| Logging | Run ID, stage, latency, query count, token, chi phí ước tính, lỗi; không log secret |

Kiểm tra và dự trù ngân sách trước mỗi call, đối chiếu usage sau call; nhiều hội thoại của cùng Builder không được vượt ngân sách do race condition. Không gửi bảng thô hoặc kết quả chi tiết cho LLM khi catalog/ngữ cảnh đã đủ. Lỗi 429, timeout, JSON sai, hết quota và lỗi một widget phải có thông báo có cấu trúc; bản đã duyệt không bị ghi đè.

## 3. Cấu trúc file triển khai dự kiến

Các đường dẫn dưới đây là mục tiêu tổ chức code sau này. Chỉ `IMPLEMENTATION_PLAN.md` được tạo trong yêu cầu hiện tại.

```text
IMPLEMENTATION_PLAN.md
README.md
.gitignore
data/real-estate-sales-sample-database-v3-sql-postgres.sql  # giữ nguyên
docs/
  data-audit.md, data-dictionary.md, kpi-catalog.md
  acceptance-report.md, local-runbook.md
scripts/
  start-local.ps1, backup-db.ps1, restore-db.ps1
backend/
  pyproject.toml, requirements.lock, .env.example, alembic.ini
  alembic/env.py
  alembic/versions/
  app/
    main.py, config.py
    db/connections.py, db/models.py
    schemas/analysis.py, schemas/dashboard.py, schemas/agent.py
    auth/passwords.py, auth/sessions.py, auth/dependencies.py
    api/auth.py, api/catalog.py, api/dashboards.py, api/conversations.py
    analytics/catalog.py, analytics/compiler.py
    analytics/validator.py, analytics/executor.py
    services/dashboard.py, services/conversation.py
    services/approval.py, services/usage.py
    agent/state.py, agent/graph.py, agent/nodes.py
    agent/prompts.py, agent/llm.py, agent/mock.py, agent/checkpoints.py
  scripts/audit_db.py, scripts/seed_users.py, scripts/seed_dashboard.py
  scripts/export_openapi.py, scripts/evaluate_agent.py
  tests/unit/, tests/integration/, tests/fixtures/, tests/evaluation/
frontend/
  package.json, package-lock.json, .env.example, next.config.ts
  src/app/layout.tsx, src/app/globals.css
  src/app/login/page.tsx, src/app/dashboards/page.tsx
  src/app/dashboards/[id]/page.tsx, src/app/builder/page.tsx
  src/components/dashboard/, src/components/builder/
  src/lib/api.ts, src/lib/format.ts, src/types/api.generated.ts
  playwright.config.ts, tests/e2e/
```

### 3.1. API và kiểu dữ liệu chung

Pydantic là nguồn chuẩn của OpenAPI; sinh TypeScript types từ OpenAPI. Không duy trì hai bộ định nghĩa khác nhau bằng tay.

| Kiểu | Trách nhiệm |
|---|---|
| AnalysisPlan | KPI, dimension, filter, khoảng ngày, sort, limit |
| DashboardSpec | schema/catalog version, title, layout, widgets, query references, filters |
| WidgetSpec | ID ổn định, loại, nhãn, đơn vị, mapping dữ liệu |
| QueryResult | Cột/kiểu, rows, latency, cảnh báo, trạng thái dữ liệu |
| AgentState | Ngữ cảnh, current spec, draft, base version, trạng thái duyệt |
| RunUsage | LLM calls, token, chi phí ước tính, SQL count, latency, lỗi |

| Endpoint | Quyền/hành vi |
|---|---|
| POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me | Đăng nhập/đăng xuất/phiên hiện tại |
| GET /api/catalog | Catalog được hỗ trợ theo quyền; thông tin SQL chi tiết chỉ Builder |
| POST /api/conversations | Builder tạo hội thoại mới hoặc sửa dashboard sở hữu |
| POST /api/conversations/{id}/messages | Builder sở hữu; trả preview, clarification hoặc structured error |
| GET /api/conversations/{id} | Builder sở hữu; phục hồi hội thoại/draft |
| POST /api/conversations/{id}/approval | Builder sở hữu; approve/reject đúng draft revision |
| GET /api/dashboards, GET /api/dashboards/{id} | Người đăng nhập; chỉ dashboard đã duyệt |
| POST /api/dashboards/{id}/query | Chạy lại theo scope phiên hiện tại và filters hợp lệ |

Trạng thái Agent tối thiểu: `running`, `needs_clarification`, `awaiting_approval`, `completed`, `failed`. Từ chối duyệt kết thúc lượt mà không phát hành. Lưu lý do/kết quả riêng để phân biệt với duyệt thành công.

Metadata tối thiểu: users, sessions, dashboards, dashboard_versions, conversations/messages, usage/audit và checkpoint tables. Chỉ lưu spec chính thức làm nguồn tái thực thi; SQL đã sinh là dữ liệu truy vết. Catalog/schema version không tương thích phải báo lỗi thay vì đổi KPI ngầm.

## 4. Thứ tự triển khai và milestone

| Phase | Thứ tự task | Milestone | Ước lượng |
|---|---|---|---|
| 0 | P0-T01 → P0-T02 → P0-T03 | M0: schema/KPI/baseline rõ ràng | 2–3 ngày |
| 1 | P1-T01 → P1-T02 → P1-T03 → P1-T04 | M1: local app, login, RBAC và RLS | 3–4 ngày |
| 2 | P2-T01 → P2-T02 → P2-T03 → P2-T04 → P2-T05 | M2: dashboard từ DB không cần LLM | 4–5 ngày |
| 3 | P3-T01 → P3-T02 → P3-T03 → P3-T04 | M3: ngôn ngữ tự nhiên → draft | 4–5 ngày |
| 4 | P4-T01 → P4-T02 → P4-T03 → P4-T04 | M4: hội thoại, duyệt, phục hồi, đủ KPI | 5–7 ngày |
| 5 | P5-T01 → P5-T02 → P5-T03 → P5-T04 | M5: kiểm thử và bàn giao local | 4–6 ngày |

Bản gốc ước lượng tổng 22–30 ngày; cộng khoảng thời gian từng phase cho kết quả **22–30 ngày làm việc**, chưa tính chờ credentials/LLM hoặc phản hồi nghiệp vụ. Thực hiện theo thứ tự trên; chỉ chuyển milestone khi tiêu chí bắt buộc đạt hoặc có ghi nhận blocker rõ ràng. Không đánh dấu test skipped vì thiếu DB/API key thành đã đạt.

## 5. Task chi tiết và acceptance criteria

Quy ước: “Tạo” là file mới; “Sửa” là cập nhật file đã tạo ở task trước. Test files được tạo cùng task, không chờ phase 5 mới kiểm thử. Không sửa file SQL import nguồn.

### Phase 0 — Xác minh dữ liệu và chốt KPI

#### [ ] P0-T01 — Khảo sát database đang chạy

- Phụ thuộc: có kết nối read-only tới DB thật; nếu chưa có, ghi rõ blocker và chỉ khảo sát file import.
- Công việc: lấy version/schema/PK/FK/index/privilege; đếm dòng, NULL, khoảng ngày; kiểm tra quyền hiện tại, quan hệ nhiều-nhiều và fan-out; so sánh với file nguồn.
- Tạo: `backend/scripts/audit_db.py`, `docs/data-audit.md`, `docs/data-dictionary.md`.
- Acceptance criteria: báo cáo phân biệt dữ kiện DB thật với file import; liệt kê đủ 16 bảng và quan hệ; có số liệu sai lệch, duplicate/FK orphan nếu có; không thay đổi DB và không xuất secret/PII vào log.
- Kiểm thử: chạy audit trong transaction read-only, đối chiếu vài truy vấn catalog và count trực tiếp; ghi timestamp/môi trường kiểm tra.

#### [ ] P0-T02 — Định nghĩa KPI và SQL chuẩn độc lập

- Phụ thuộc: P0-T01; có thể chuẩn bị bản dự thảo theo file nhưng chưa chốt baseline DB.
- Công việc: định nghĩa bảy KPI, grain, ngày, đơn vị, dimension hợp lệ; viết SQL chuẩn cho ALL/CA/TX, các kỳ và trường hợp rỗng; giải thích không hỗ trợ đại lý/lợi nhuận.
- Tạo: `docs/kpi-catalog.md`, `backend/tests/fixtures/golden_queries.sql`, `backend/tests/fixtures/golden_results.json`.
- Sửa: `docs/data-audit.md` với baseline thực tế.
- Acceptance criteria: bốn KPI giao dịch đối soát được; DISTINCT property không nhầm transaction count; tỷ lệ accepted đúng mẫu số; số tiền khớp đến 0,01; không JOIN nhiều fact để SUM.
- Kiểm thử: chạy golden SQL độc lập với compiler dự kiến; kiểm tra ALL/CA/TX và ngày biên.

#### [x] P0-T03 — Chuẩn bị bộ câu hỏi và điều kiện nghiệm thu

- Phụ thuộc: P0-T02.
- Công việc: tạo 30 yêu cầu tiếng Việt: 20 hợp lệ, 5 mơ hồ, 5 không hỗ trợ; mỗi câu có expected KPI/dimension/filter hoặc expected clarification/refusal; xác định các kịch bản quyền, HITL và lỗi.
- Tạo: `backend/tests/evaluation/prompts.json`, `docs/acceptance-report.md` (template chưa có kết quả).
- Acceptance criteria: đủ 30 case với oracle cụ thể; case thuộc KPI phase 4 được gắn nhãn để đánh giá lại sau mở rộng; không chấm chỉ bằng việc SQL chạy không lỗi.
- Kiểm thử: review coverage theo catalog và kịch bản demo; xác minh JSON đọc được.

### Phase 1 — Nền tảng local và phân quyền

#### [x] P1-T01 — Scaffold và cấu hình local

- Phụ thuộc: M0 để tích hợp dữ liệu; có thể chuẩn bị scaffold khi audit bị chặn.
- Công việc: khởi tạo Git; scaffold Next.js/FastAPI; cấu hình env, health check, API proxy cùng origin, dependency lock và lệnh chạy Windows.
- Tạo: `.gitignore`, `README.md`, `backend/pyproject.toml`, `backend/requirements.lock`, `backend/.env.example`, `backend/app/main.py`, `backend/app/config.py`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/next.config.ts`, `frontend/.env.example`, `frontend/src/app/layout.tsx`, `frontend/src/app/globals.css`, `scripts/start-local.ps1`.
- Acceptance criteria: FE :3000 gọi health BE :8000 qua /api; config thiếu có lỗi rõ ràng; secrets/.env/backup bị ignore; chưa cần LLM key để khởi động.
- Kiểm thử: backend health smoke test, frontend typecheck/build, startup từ hướng dẫn README.

#### [ ] P1-T02 — Schema metadata và migration an toàn

- Phụ thuộc: P1-T01, P0-T01 và thông tin tài khoản migration.
- Công việc: cấu hình Alembic; tạo schema app/analytics, models và connection metadata; chuẩn bị bảng users/sessions/dashboard versions/conversations/usage; kiểm tra backup trước khi migration DB đang có.
- Tạo: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_app_schema.py`, `backend/app/db/connections.py`, `backend/app/db/models.py`, `scripts/backup-db.ps1`, `backend/tests/integration/test_migrations.py`.
- Sửa: `backend/app/config.py`, `backend/.env.example`, `README.md`.
- Acceptance criteria: migration chạy trên bản DB test; không xóa/import lại bảng nguồn; credential runtime không có quyền DDL; backup được kiểm tra trước thao tác lên DB hiện có; bản ghi version và ràng buộc uniqueness phục vụ approval idempotent được định nghĩa.
- Kiểm thử: upgrade DB test từ schema mẫu; kiểm tra số dòng nguồn trước/sau; kiểm tra restore backup vào database test tách biệt trước khi sửa DB thật.

#### [ ] P1-T03 — View analytics, reader roles và RLS

- Phụ thuộc: P1-T02, P0-T02.
- Công việc: tạo reader roles ALL/CA/TX, grants tối thiểu, policies trên properties và ba fact; tạo sales view trước, chuẩn bị offers/repairs cho phase 4; cấp connection pool theo profile server.
- Tạo: `backend/alembic/versions/0002_analytics_security.py`, `backend/tests/integration/test_rls.py`.
- Sửa: `backend/app/db/connections.py`, `backend/.env.example`, `docs/local-runbook.md` (tạo nếu chưa có).
- Acceptance criteria: SELECT trực tiếp và qua view bằng reader CA/TX chỉ thấy đúng bang; không đổi role để đọc ALL; INSERT/UPDATE/DELETE/DDL bị từ chối; không đọc được cột PII; app runtime không dùng owner cho analytics; thiếu scope mặc định bị chặn.
- Kiểm thử: test bằng credential reader thật, không dùng superuser giả lập; đối soát totals CA/TX; kiểm tra offers/repairs không lộ qua property join.

#### [ ] P1-T04 — Đăng nhập, phiên, RBAC và tài khoản demo

- Phụ thuộc: P1-T03.
- Công việc: Argon2, session server-side, login/logout/me, cookie HttpOnly/SameSite, Origin checks; seed bốn tài khoản; trang login và trạng thái người dùng; dependency kiểm tra role/ownership tái sử dụng.
- Tạo: `backend/app/auth/passwords.py`, `backend/app/auth/sessions.py`, `backend/app/auth/dependencies.py`, `backend/app/api/auth.py`, `backend/scripts/seed_users.py`, `backend/tests/integration/test_auth.py`, `frontend/src/app/login/page.tsx`, `frontend/src/lib/api.ts`.
- Sửa: `backend/app/main.py`, `backend/app/config.py`, `frontend/src/app/layout.tsx`, `README.md`.
- Acceptance criteria: sai mật khẩu/hết hạn/chưa đăng nhập bị chặn; logout vô hiệu phiên server; role/profile đọc từ server; seed lặp không tạo trùng; lỗi auth không lộ password/token; mutation từ origin không hợp lệ bị chặn.
- Kiểm thử: API trực tiếp cho từng role; cookie flags; session expiry; sửa role/profile trong request không đổi quyền.

### Phase 2 — Dashboard end-to-end không cần LLM

#### [ ] P2-T01 — Contracts và KPI catalog có version

- Phụ thuộc: M1, P0-T02.
- Công việc: Pydantic schemas, bốn KPI sales, mapping dimension/view, semantic validation, API catalog; xuất OpenAPI và sinh TypeScript.
- Tạo: `backend/app/schemas/analysis.py`, `backend/app/schemas/dashboard.py`, `backend/app/schemas/agent.py`, `backend/app/analytics/catalog.py`, `backend/app/api/catalog.py`, `backend/scripts/export_openapi.py`, `backend/tests/unit/test_catalog.py`, `frontend/src/types/api.generated.ts`.
- Sửa: `backend/app/main.py`, `frontend/package.json`.
- Acceptance criteria: unknown KPI/dimension/field bị từ chối; default ngày/đơn vị rõ ràng; catalog version bắt buộc; tiền truyền qua API không mất chính xác; generated types khớp OpenAPI.
- Kiểm thử: schema validation hợp lệ/không hợp lệ, round-trip Decimal, regeneration/typecheck.

#### [ ] P2-T02 — SQL compiler và AST validator

- Phụ thuộc: P2-T01.
- Công việc: biên dịch plan sang SELECT tham số hóa, mapping KPI/dimension cố định; validate AST, nguồn, hàm và cấu trúc; không nhận arbitrary SQL.
- Tạo: `backend/app/analytics/compiler.py`, `backend/app/analytics/validator.py`, `backend/tests/unit/test_compiler.py`, `backend/tests/unit/test_sql_validator.py`.
- Acceptance criteria: bốn KPI đúng grain; filter là bound parameters; giá trị có quote hoặc SQL injection không thành code; chặn multi-statement, DML/DDL, hàm/bảng ngoài allowlist, CTE gây side effect; không ghép raw identifier từ prompt.
- Kiểm thử: kết quả compiler đối chiếu golden SQL bằng dữ liệu; negative fixtures cho các kiểu vượt allowlist, kể cả SELECT chứa hàm nguy hiểm.

#### [ ] P2-T03 — Query executor và giới hạn DB

- Phụ thuộc: P2-T02, P1-T03.
- Công việc: chọn reader pool theo user scope; transaction read-only, timeout, EXPLAIN gate; giới hạn dòng, metadata kết quả, xử lý lỗi/empty; hiệu chỉnh planner-cost threshold.
- Tạo: `backend/app/analytics/executor.py`, `backend/tests/integration/test_executor.py`.
- Sửa: `backend/app/config.py`, `backend/.env.example`, `docs/data-audit.md`.
- Acceptance criteria: totals/golden cases khớp đến 0,01; timeout 5 giây có thông báo; vượt 1.000 dòng không âm thầm cắt; query cost quá mức bị chặn; pool không rò scope giữa request; empty ratio không chia 0.
- Kiểm thử: ALL/CA/TX, scope/filter không giao nhau, ngày biên, timeout, row limit, EXPLAIN threshold và lỗi DB.

#### [ ] P2-T04 — Lưu cấu hình dashboard và truy vấn theo người xem

- Phụ thuộc: P2-T03.
- Công việc: service lưu spec/version, list/detail/query APIs, filter validation; tạo dashboard mẫu đã duyệt qua seed để kiểm thử end-to-end trước khi có luồng HITL.
- Tạo: `backend/app/services/dashboard.py`, `backend/app/api/dashboards.py`, `backend/scripts/seed_dashboard.py`, `backend/tests/integration/test_dashboards.py`.
- Sửa: `backend/app/main.py`, `backend/app/db/models.py` (thêm migration nếu schema đã áp dụng).
- Acceptance criteria: list/detail chỉ trả bản chính thức; query dùng quyền viewer, không trả snapshot Builder; version không tương thích báo lỗi; Viewer không tạo/sửa spec qua API; seed mẫu không là đường bỏ qua approval trong runtime.
- Kiểm thử: cùng dashboard mở bằng Viewer ALL/CA cho đúng totals; request sửa SQL/profile/user ID bị từ chối hoặc không ảnh hưởng quyền.

#### [ ] P2-T05 — Giao diện dashboard và ECharts renderer

- Phụ thuộc: P2-T04.
- Công việc: list/detail dashboard, filters ngày/bang/loại, card/chart/table, CSS Grid; loading/empty/error per widget; format tiền và đơn vị.
- Tạo: `frontend/src/app/dashboards/page.tsx`, `frontend/src/app/dashboards/[id]/page.tsx`, `frontend/src/components/dashboard/DashboardGrid.tsx`, `frontend/src/components/dashboard/ChartWidget.tsx`, `frontend/src/components/dashboard/KpiCard.tsx`, `frontend/src/components/dashboard/Filters.tsx`, `frontend/src/lib/format.ts`, `frontend/tests/e2e/dashboard.spec.ts`.
- Sửa: `frontend/src/lib/api.ts`, `frontend/src/app/globals.css`.
- Acceptance criteria: ba card + ít nhất ba chart lấy dữ liệu thật; hỗ trợ toàn bộ loại widget đã chốt; biểu đồ resize đúng; không eval nội dung; ngày/phạm vi/đơn vị hiển thị; empty scope có thông báo rõ; Viewer không thấy nút Agent/duyệt.
- Kiểm thử: build/typecheck, Playwright filter và totals, nhãn dài/HTML text, viewport resize, lỗi một widget.

### Phase 3 — Ngôn ngữ tự nhiên tạo dashboard

#### [ ] P3-T01 — LLM adapter, mock và prompt structured output

- Phụ thuộc: M2.
- Công việc: định nghĩa adapter trả plan/clarification/unsupported, mock deterministic; prompt kèm catalog và schema; tích hợp một provider có endpoint/model/key được cấu hình; không gửi raw dataset.
- Tạo: `backend/app/agent/llm.py`, `backend/app/agent/mock.py`, `backend/app/agent/prompts.py`, `backend/tests/unit/test_llm_adapter.py`.
- Sửa: `backend/app/config.py`, `backend/.env.example`, `backend/pyproject.toml`, `backend/requirements.lock`.
- Acceptance criteria: chạy mock không cần key; mode thật thiếu cấu hình bị chặn; output validate bằng Pydantic; KPI ngoài catalog không tự bịa; adapter không có quyền DB hay thực thi SQL.
- Kiểm thử: mock outputs, JSON sai, unsupported, clarification, provider timeout/429 giả lập; smoke call thật chỉ khi có credential và bảng giá.

#### [ ] P3-T02 — Usage, token và ngân sách trước mỗi call

- Phụ thuộc: P3-T01.
- Công việc: đếm calls/tokens, reserve ngân sách trước call, reconcile sau call, deadline và một vòng sửa output; ghi audit không có secret.
- Tạo: `backend/app/services/usage.py`, `backend/tests/unit/test_usage.py`, `backend/tests/integration/test_budget.py`.
- Sửa: `backend/app/agent/llm.py`, `backend/app/config.py`, `backend/app/db/models.py` (migration mới nếu cần).
- Acceptance criteria: áp giới hạn ba calls/24.000 token/60 giây; 0,10 USD/lượt và 1 USD/ngày; thiếu pricing không bật live mode; retry tính vào cùng ngân sách; requests đồng thời không vượt budget; ghi chi phí ước tính, không khẳng định là hóa đơn chính xác.
- Kiểm thử: budget boundary, retry, missing usage, timeout, nhiều lượt cùng user và ngày theo múi giờ đã chốt.

#### [ ] P3-T03 — LangGraph và API tạo preview

- Phụ thuộc: P3-T02, P2-T04.
- Công việc: các node context/plan/validate/compile/execute/preview; state có kiểu; API conversation/message/get; ownership, one-active-run, error mapping. Phase này chỉ tạo draft, chưa phát hành.
- Tạo: `backend/app/agent/state.py`, `backend/app/agent/graph.py`, `backend/app/agent/nodes.py`, `backend/app/services/conversation.py`, `backend/app/api/conversations.py`, `backend/tests/integration/test_agent.py`.
- Sửa: `backend/app/main.py`, `backend/app/schemas/agent.py`.
- Acceptance criteria: prompt hợp lệ tạo spec tối đa tám widget/sáu query; mơ hồ trả needs_clarification; unsupported không query; Viewer/khác owner bị chặn; running lượt thứ hai không ghi đè; lỗi giữ dashboard chính thức nguyên vẹn.
- Kiểm thử: mock graph end-to-end; prompt injection yêu cầu đổi scope, bỏ validation hoặc chạy SQL tùy ý không vượt quyền; query output so với golden results.

#### [ ] P3-T04 — Giao diện Builder và đánh giá 30 câu hỏi

- Phụ thuộc: P3-T03, P0-T03; provider thật sẵn sàng để nghiệm thu chất lượng LLM.
- Công việc: chat input, preview, clarification UI, thông báo quota/lỗi, nguồn KPI/SQL cho Builder; script đánh giá plan và số liệu.
- Tạo: `frontend/src/app/builder/page.tsx`, `frontend/src/components/builder/ChatPanel.tsx`, `frontend/src/components/builder/PreviewPanel.tsx`, `backend/scripts/evaluate_agent.py`, `frontend/tests/e2e/builder.spec.ts`.
- Sửa: `frontend/src/lib/api.ts`, `frontend/src/types/api.generated.ts`, `docs/acceptance-report.md`.
- Acceptance criteria: ít nhất 18/20 câu hợp lệ đúng plan trong bộ sales cho M3; 5 mơ hồ và 5 không hỗ trợ được xử lý đúng; mọi query thực thi cho kết quả đúng; kết quả mock và LLM thật được báo cáo riêng. Nếu bộ đầy đủ có offers/repairs, đánh giá lại tại P4-T04.
- Kiểm thử: chạy evaluator, lưu model/cấu hình/ngày/usage và kết quả từng case; Playwright tạo dashboard tiếng Việt. Thiếu key thì ghi live evaluation chưa chạy, không tuyên bố M3 hoàn tất.

### Phase 4 — Hội thoại, HITL và đủ KPI MVP

#### [ ] P4-T01 — Chỉnh sửa theo hội thoại và ngữ cảnh ổn định

- Phụ thuộc: M3.
- Công việc: tải current spec và history có giới hạn; chỉnh filter/chart/thêm-bớt widget; giữ ID và nội dung widget không bị sửa; bắt đầu sửa dashboard sở hữu từ bản đã duyệt; trả diff của draft.
- Tạo: `backend/tests/integration/test_conversation_edits.py`, `frontend/src/components/builder/DraftChanges.tsx`.
- Sửa: `backend/app/services/conversation.py`, `backend/app/agent/state.py`, `backend/app/agent/prompts.py`, `backend/app/agent/nodes.py`, `frontend/src/components/builder/ChatPanel.tsx`.
- Acceptance criteria: ít nhất năm lượt chỉnh sửa giữ ngữ cảnh đúng; thay cách vẽ không truy vấn lại nếu query/filter/scope còn nguyên; đổi filter làm số liệu tính lại; widget không liên quan giữ nguyên; không gửi lịch sử vô hạn vượt token budget.
- Kiểm thử: chuỗi edit deterministic và LLM, reset filter, tham chiếu “biểu đồ này” mơ hồ cần làm rõ, sửa dashboard người khác bị chặn.

#### [ ] P4-T02 — Checkpoint PostgreSQL và phục hồi khi restart

- Phụ thuộc: P4-T01.
- Công việc: tích hợp durable checkpointer, mapping conversation–thread phía server, interrupt ở chờ duyệt; khôi phục draft/history; xử lý run dở dang khi process dừng.
- Tạo: `backend/app/agent/checkpoints.py`, `backend/tests/integration/test_checkpoint_recovery.py`.
- Sửa: `backend/app/agent/graph.py`, `backend/app/services/conversation.py`, `backend/app/db/connections.py`, `backend/app/main.py`; migration mới cho schema/checkpointer nếu cần.
- Acceptance criteria: dừng/khởi động BE tại awaiting_approval vẫn lấy đúng draft; owner check xảy ra trước truy cập checkpoint; không giữ transaction mở khi chờ người dùng; run bị ngắt được phục hồi/báo lỗi có kiểm soát, không chạy treo vô hạn.
- Kiểm thử: restart process thật trong test local, khôi phục same thread, truy cập thread khác owner, resume không lặp query/side effect ngoài dự kiến.

#### [ ] P4-T03 — Duyệt, từ chối và lưu phiên bản idempotent

- Phụ thuộc: P4-T02, P2-T04.
- Công việc: approval API validate revision/hash/base version; publish transaction, uniqueness/idempotency và audit; UI approve/reject, diff và xung đột; resume graph an toàn khi DB publish đã hoàn thành nhưng response bị mất.
- Tạo: `backend/app/services/approval.py`, `backend/tests/integration/test_approval.py`, `frontend/src/components/builder/ApprovalPanel.tsx`.
- Sửa: `backend/app/api/conversations.py`, `backend/app/services/dashboard.py`, `backend/app/agent/graph.py`, `frontend/src/app/builder/page.tsx`; thêm migration constraints nếu cần.
- Acceptance criteria: chỉ đúng owner Builder duyệt được draft hiện tại; reject không phát hành; stale draft/base version trả 409; double click/retry/resume sau crash chỉ tạo một version; Viewer tiếp tục thấy bản cũ trước khi duyệt, thấy bản mới sau khi duyệt; draft không lộ trong list/detail.
- Kiểm thử: approval lặp, đồng thời, edit sau preview, mất response sau commit, restart rồi retry, quyền Viewer/khác owner.

#### [ ] P4-T04 — KPI offers/repairs và kiểm thử hồi quy

- Phụ thuộc: P4-T03, P0-T02, policies từ P1-T03.
- Công việc: mở ba KPI còn lại, view theo grain riêng, dimension validation, đơn vị/format; tăng catalog version có chiến lược đọc bản cũ; mở rộng evaluation.
- Tạo: `backend/alembic/versions/0003_offer_repair_views.py` nếu view chưa có, `backend/tests/integration/test_offer_repair_kpis.py`.
- Sửa: `backend/app/analytics/catalog.py`, `backend/app/analytics/compiler.py`, `docs/kpi-catalog.md`, `backend/tests/fixtures/golden_queries.sql`, `backend/tests/fixtures/golden_results.json`, `backend/tests/evaluation/prompts.json`, `docs/acceptance-report.md`.
- Acceptance criteria: offer_count/accepted rate/repair cost đúng ngày và grain; số tiền sales không tăng do fan-out; scope đúng cả ba fact; agent từ chối dimension không hợp lệ; catalog cũ không âm thầm đổi nghĩa; chạy lại bộ 30 case đầy đủ đạt ngưỡng.
- Kiểm thử: compare independent SQL, accepted/empty denominator, ALL/CA/TX, mixed-fact dashboard với query tách biệt và regression bốn KPI sales.

### Phase 5 — Kiểm thử, hiệu năng và bàn giao

#### [ ] P5-T01 — Bộ test bảo mật và tính đúng bắt buộc

- Phụ thuộc: M4.
- Công việc: tổng hợp kiểm thử IDOR/RBAC/RLS, PII, SQL allowlist, prompt injection, CSRF/Origin, nguồn KPI và approval; sửa lỗi phát hiện bằng task bug có liên kết test.
- Tạo: `backend/tests/integration/test_security_matrix.py`, `backend/tests/unit/test_adversarial_plans.py`.
- Sửa: các module liên quan khi test phát hiện lỗi; `docs/acceptance-report.md`.
- Acceptance criteria: toàn bộ test quyền/KPI/HITL pass; không có test bắt buộc bị skip vì thiếu DB; không thể truy cập ngoài scope qua list/query/conversation/checkpoint/approval; không log secret.
- Kiểm thử: pytest unit và integration trên DB test riêng; role thực tế, không mock RLS; so baseline nguồn trước/sau để xác nhận không bị sửa.

#### [ ] P5-T02 — Playwright end-to-end và khả năng phục hồi

- Phụ thuộc: P5-T01.
- Công việc: chạy hành trình Builder tạo–sửa–duyệt, Viewer mở–lọc; mô phỏng lỗi mạng/provider/DB, session expiry, restart; kiểm tra loading/empty/widget error/resize.
- Tạo: `frontend/playwright.config.ts`, `frontend/tests/e2e/full-journey.spec.ts`, `frontend/tests/e2e/permissions.spec.ts`, `frontend/tests/e2e/recovery.spec.ts` (config có thể đã tạo tối thiểu ở P2-T05).
- Sửa: `frontend/package.json`, `docs/acceptance-report.md` và module có lỗi.
- Acceptance criteria: kịch bản năm lượt hoàn tất; Viewer CA không thấy dữ liệu TX/ALL vượt scope; restart chờ duyệt không mất draft; lỗi một widget có thông báo, không phá trang; HTML trong nhãn chỉ là text.
- Kiểm thử: chạy với mock deterministic trong regression và một smoke journey với provider thật; lưu bằng chứng UI và kết quả riêng.

#### [ ] P5-T03 — Đo latency, ngân sách và tài nguyên

- Phụ thuộc: P5-T02, provider thật đã cấu hình.
- Công việc: đo riêng DB/LLM/render, P95 và usage; kiểm tra concurrency budgets, timeout/cost gates; ghi cấu hình máy/model/dataset.
- Tạo: `backend/scripts/benchmark.py`, `backend/tests/integration/test_resource_limits.py`.
- Sửa: `docs/acceptance-report.md`; giới hạn cấu hình chỉ điều chỉnh có bằng chứng.
- Acceptance criteria: dashboard đã lưu P95 < 3 giây, tạo AI P95 < 45 giây trên dataset mẫu; đo ít nhất 30 lượt cho từng nhóm và công bố số mẫu; tất cả giới hạn hard vẫn được thực thi. Nếu chưa đạt, ghi số đo và nguyên nhân, chưa đánh dấu đạt hiệu năng.
- Kiểm thử: warm-up riêng, đo từ request tới kết quả có thể hiển thị, ghi error rate, số queries và tokens; không suy ra latency chỉ từ EXPLAIN cost.

#### [ ] P5-T04 — Runbook, backup/restore và bàn giao MVP

- Phụ thuộc: P5-T03; các gate bắt buộc ở P5-T01/P5-T02 đạt.
- Công việc: hướng dẫn setup sạch, env, migrations, seed, khởi động, cấu hình provider, tài khoản demo, test; phục hồi backup vào DB riêng; ghi limitations và kết quả thực tế.
- Tạo: `scripts/restore-db.ps1`.
- Sửa: `README.md`, `docs/local-runbook.md`, `docs/acceptance-report.md`, `backend/.env.example`, `frontend/.env.example`, `IMPLEMENTATION_PLAN.md` (cập nhật trạng thái task khi đã thực hiện).
- Acceptance criteria: người khác chạy local theo README từ môi trường sạch; không cần đoán lệnh hoặc secret; backup phục hồi được vào DB test; có thông tin catalog/model/config và test report; không có secret trong repository; mỗi task có kết quả kiểm chứng hoặc blocker cụ thể.
- Kiểm thử: thực hiện lại checklist setup và restore trên môi trường test, demo kịch bản nghiệm thu chính; không tự triển khai cloud.

## 6. Ma trận nghiệm thu tổng thể

| Nhóm | Điều kiện bắt buộc | Task chịu trách nhiệm |
|---|---|---|
| Dữ liệu | DB thật được đối chiếu, chênh lệch ghi rõ, golden SQL độc lập | P0-T01, P0-T02 |
| KPI | Đúng grain, ngày, Decimal, DISTINCT, mẫu số; không fan-out | P2-T02, P2-T03, P4-T04 |
| Quyền | Viewer/Builder, ownership và ALL/CA/TX được thực thi cả API/DB | P1-T03, P1-T04, P5-T01 |
| SQL | Allowlist, parameters, read-only, timeout, cost/row limit | P2-T02, P2-T03 |
| LLM | ≥18/20 plan hợp lệ đúng; 10 case còn lại xử lý đúng; mọi số liệu đã chạy đúng | P3-T04, P4-T04 |
| Hội thoại | Ít nhất năm lượt, ID widget ổn định, ngữ cảnh và thay đổi đúng | P4-T01 |
| HITL | Không phát hành trước duyệt; stale 409, retry không trùng; restart phục hồi | P4-T02, P4-T03 |
| Ngân sách | Chặn trước mỗi call, tính retry, chống race, log usage | P3-T02, P5-T03 |
| UI | Chart types, filter, loading/empty/error, resize, text an toàn | P2-T05, P5-T02 |
| Hiệu năng | P95 dashboard <3 giây; AI <45 giây, có số đo và môi trường | P5-T03 |
| Bàn giao | README/env/runbook, backup restore đã thử, báo cáo trung thực | P5-T04 |

### 6.1. Kịch bản demo nghiệm thu cuối

1. Đăng nhập Builder ALL, tạo dashboard “giá trị giao dịch năm 2025 theo tháng, bang và loại bất động sản”.
2. Kiểm tra ba KPI card và ba biểu đồ, nguồn KPI, SQL và khoảng thời gian.
3. Chỉnh qua ít nhất năm lượt: lọc California; đổi loại bất động sản thành cột ngang; thêm số bất động sản có giao dịch; bỏ một widget; đổi khoảng thời gian. Đối soát widget không bị sửa.
4. Restart backend khi draft đang chờ duyệt; mở lại đúng hội thoại và preview.
5. Duyệt draft hiện tại, thử lại cùng approval; chỉ một phiên bản được phát hành.
6. Đăng nhập Viewer CA, mở bản đã duyệt, đổi filter hợp lệ; thử TX cho trạng thái không có dữ liệu trong phạm vi.
7. Thử gọi API tạo/sửa/duyệt bằng Viewer và lấy draft bằng tài khoản khác; đều bị chặn.
8. Builder sửa dashboard đã lưu; Viewer vẫn thấy version trước cho đến lần duyệt kế tiếp.

## 7. Điều kiện đầu vào, rủi ro và cách theo dõi

| Điều kiện/rủi ro | Cách xử lý và gate |
|---|---|
| Thiếu credential DB | Cấu hình local an toàn; chưa đánh dấu audit/integration/RLS đạt trước khi kiểm tra DB thật |
| Thay RLS trên DB hiện có | Audit grants/consumer trước; backup và thử migration/restore trên DB test; không đổi dữ liệu nguồn |
| Chưa có provider/model/key/pricing | Phase 1–2 dùng mock; live evaluation/latency chưa thể nghiệm thu; chốt cấu hình trước phase 3 live |
| Dataset synthetic và JOIN mơ hồ | Dùng fact/catalog đã kiểm chứng; loại đại lý/neighbourhood JOIN khỏi MVP |
| Tiền tệ chưa xác nhận | Giữ nhãn trung tính, không quy đổi hoặc tự đặt USD |
| Version dashboard/catalog thay đổi | Kiểm tra tương thích; không âm thầm đổi định nghĩa KPI đã duyệt |
| Crash giữa publish và graph resume | Publish idempotent, unique constraint; retry khôi phục cùng kết quả |

Mỗi task chỉ đánh dấu hoàn tất khi file cần thiết đã tồn tại, acceptance criteria được kiểm chứng và kết quả được ghi trong `docs/acceptance-report.md`. Không xem mock thành công là bằng chứng LLM thật đạt chất lượng; không xem API filter đúng là bằng chứng RLS đúng. Công việc trong yêu cầu hiện tại kết thúc ở việc tạo tài liệu này.

## 8. Tài liệu tham chiếu từ kế hoạch đã thống nhất

- Dataset cục bộ: `data/real-estate-sales-sample-database-v3-sql-postgres.sql`.
- PostgreSQL 16 RLS: https://www.postgresql.org/docs/16/ddl-rowsecurity.html
- PostgreSQL 16 CREATE VIEW / security_invoker: https://www.postgresql.org/docs/16/sql-createview.html
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence

Khi triển khai, kiểm tra API của phiên bản thư viện được pin; các link tham chiếu không thay thế test trên phiên bản thực tế.
