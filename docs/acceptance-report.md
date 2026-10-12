# Báo cáo nghiệm thu MVP — template

> Trạng thái: **PARTIAL**. P0-T01 đã chạy audit file import, P0-T02 đã kiểm chứng catalog/golden fixture trên cùng file, P0-T03 và P1-T01 đã đạt acceptance riêng; P1-T02 và P1-T03 đã có migration/static tests nhưng integration DB test vẫn `BLOCKED` do thiếu credential và backup đã restore. Các mục `BLOCKED`/`NOT_RUN` không được tính là đạt. Mock, test skipped, SQL chỉ chạy không lỗi, hoặc kết quả từ file import không thay thế kiểm chứng DB/LLM thật.

## 1. Thông tin lần chạy

| Trường | Giá trị |
|---|---|
| Report ID | `<run-id>` |
| Ngày/giờ Asia/Ho_Chi_Minh | `<yyyy-mm-dd hh:mm:ss>` |
| Commit/revision | `<sha-or-worktree-id>` |
| Người chạy | `<name>` |
| Máy/OS/CPU/RAM | `<environment>` |
| Frontend version | `<version>` |
| Backend version | `<version>` |
| PostgreSQL version/database | `<verified-live-value>` |
| Dataset hash/row baseline | `<sha256-and-baseline>` |
| Catalog version | `<catalog-version>` |
| LLM mode/provider/model | `<mock-or-live/provider/model>` |
| Pricing config | `<source-and-date-or-not-applicable>` |

## 2. Nguyên tắc kết luận

- Trạng thái cho từng gate: `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`; không dùng `SKIP` như `PASS`.
- Mỗi `PASS` phải có command/test ID và artifact hoặc log không chứa secret/PII.
- Kết quả mock và provider thật báo riêng. Mock pass không chứng minh chất lượng LLM thật.
- Baseline file import và DB thật báo riêng. Chênh lệch phải được giải thích, không sửa dữ liệu để ép khớp.
- Plan đúng phải khớp KPI, dimension, filter, kỳ, chart, scope và authorization oracle. “SQL chạy được” chưa đủ.
- KPI tiền so bằng Decimal đến 0,01; tỷ lệ kiểm tra cả tử số và mẫu số; không chấp nhận fan-out.

## 3. Trạng thái milestone

| Milestone | Điều kiện | Trạng thái | Bằng chứng/blocker |
|---|---|---|---|
| M0 | Schema, bảy KPI, baseline và bộ 30 case rõ ràng | `NOT_RUN` | `<links/commands>` |
| M1 | Local app, login, RBAC và RLS | `NOT_RUN` | `<links/commands>` |
| M2 | Dashboard từ DB không cần LLM | `NOT_RUN` | `<links/commands>` |
| M3 | Ngôn ngữ tự nhiên → draft | `NOT_RUN` | `<links/commands>` |
| M4 | Hội thoại, duyệt, phục hồi, đủ KPI | `NOT_RUN` | `<links/commands>` |
| M5 | Test và bàn giao local | `NOT_RUN` | `<links/commands>` |

### 3.1. P1-T01 — scaffold và cấu hình local

| Kiểm tra | Actual | Trạng thái | Bằng chứng |
|---|---|---|---|
| Backend health trực tiếp | `GET 127.0.0.1:8000/api/health` → 200, payload `status=ok` | `PASS` | `backend/tests/test_scaffold.py`; startup smoke 12/10/2026 |
| Proxy cùng origin | `GET 127.0.0.1:3000/api/health` → cùng payload backend | `PASS` | chạy `scripts/start-local.ps1` với config từ hai file example |
| Thiếu config | Backend thiếu `APP_ENV` và frontend thiếu `BACKEND_URL` đều exit 1 với tên field/biến rõ ràng | `PASS` | config negative smoke |
| Không cần DB/LLM | App và health khởi động chỉ với `APP_ENV`; không có key/secret field trong P1 config | `PASS` | `test_scaffold_needs_no_database_or_llm_secret` |
| Dependency lock | Python `pip check` không lỗi; `npm ci --dry-run` exit 0; direct dependency đều pin exact | `PASS` | `backend/requirements.lock`, `frontend/package-lock.json` |
| Backend tests | 13/13 pass | `PASS` | `.venv/Scripts/python.exe -m pytest -q` |
| Frontend quality gates | lint, typecheck và production build đều exit 0 | `PASS` | `npm run lint`; `npm run typecheck`; `npm run build` |
| Ignore local artifacts | `.env`, `.env.local`, runtime log và database backup đều được ignore | `PASS` | `git check-ignore -v ...` |
| Startup/cleanup | Script mở đúng cổng 8000/3000; Ctrl+C dừng cả hai, hai cổng được giải phóng | `PASS` | local startup smoke; không để lại env tạm |

Kết luận P1-T01: **PASS**. Đây chỉ là scaffold/health; M1 vẫn `NOT_RUN` cho tới khi P1-T02–P1-T04 hoàn tất.

### 3.2. P1-T02 — schema metadata và migration an toàn

| Kiểm tra | Actual | Trạng thái | Bằng chứng/blocker |
|---|---|---|---|
| Metadata app | 9 bảng trong schema `app`; `analytics` được tạo rỗng cho task sau; không model nguồn `public` | `PASS` | `test_metadata_is_confined_to_app_schema` |
| Version/idempotency constraints | Unique dashboard/version, dashboard/draft hash, approval key, checkpoint identity và usage run; composite FK buộc `current_version_id` thuộc chính dashboard đó | `PASS` | `test_version_and_approval_idempotency_constraints_exist`; Alembic offline SQL |
| Credential separation | Runtime/migration dùng hai biến SecretStr; URL rỗng được coi là unset; từng operation chỉ đòi credential liên quan; cùng username và injected Alembic connection bị từ chối | `PASS` | `test_migration_requires_backup_and_separate_role`; `test_blank_urls_are_unset_and_operation_credentials_are_independent`; `test_injected_alembic_connection_is_rejected` |
| Backup gate | Alembic từ chối khi chưa có `MIGRATION_BACKUP_VERIFIED=true`; backup script hỗ trợ scheme psycopg, không đưa URL vào command line và fail-closed với query/fragment thay vì bỏ tùy chọn | `PASS` | `test_backup_script_rejects_url_options_instead_of_discarding_them`; PowerShell parser 0 lỗi |
| SQL migration/autogenerate offline | Tạo `app`/`analytics` và metadata; ownership filter loại reflected `public` table, không thể đề xuất DROP bảng nguồn | `PASS` | `test_autogenerate_filters_reflected_public_tables`; `test_offline_migration_sql_only_creates_owned_schemas` |
| Upgrade → upgrade → downgrade → upgrade | Chưa chạy trên database test đã restore | `BLOCKED` | thiếu `MIGRATION_TEST_DATABASE_URL` và `MIGRATION_TEST_BACKUP_RESTORED=true`; integration test skip |
| Row count nguồn trước/sau | Chưa đối chiếu bằng PostgreSQL integration | `BLOCKED` | cùng blocker DB test; test được định nghĩa trong `backend/tests/integration/test_migrations.py` |
| Runtime không có DDL/owner/superuser/BYPASSRLS | Test đã kiểm database/public/app/analytics CREATE, relation/schema ownership, DDL âm trong transaction và mọi role kế thừa có thể `SET ROLE` (gồm database CREATE và relation ownership), nhưng chưa chạy bằng role runtime thật | `BLOCKED` | thiếu `RUNTIME_TEST_DATABASE_URL`; integration test skip |
| Backup restore vào DB riêng | Chưa có credential/target DB test để restore | `BLOCKED` | không chạy backup hay migration trên DB localhost chưa rõ quyền |

Kết quả suite tại lần review P1-T02: 23 pass, 2 skip có blocker; Alembic offline và PowerShell parser đều exit 0. Kết luận P1-T02: **BLOCKED**; không đánh dấu task hoàn tất cho tới khi toàn bộ integration/restore/privilege checks đạt trên DB test tách biệt.

### 3.3. P1-T03 — analytics views, reader roles và RLS

| Kiểm tra | Actual | Trạng thái | Bằng chứng/blocker |
|---|---|---|---|
| Reader routing | Ba URL/pool `ALL`/`CA`/`TX` tách biệt; scope thiếu/không hợp lệ bị từ chối, không fallback `ALL`; lúc mở connection kiểm principal thật, đúng duy nhất scope group, không role thừa, owner/DDL/BYPASSRLS hay quyền đọc cột ngoài allowlist | `PASS` (unit/static), live còn blocked | `test_reader_engine_has_no_default_scope_and_requires_distinct_roles`, `test_reader_factory_registers_live_principal_scope_validation` |
| Migration roles/RLS | Ba group role `NOLOGIN`, không password; 12 SELECT policies trên `properties`, `transactions`, `offers`, `repairs`; migration fail-closed nếu gặp RLS/role có trước, `PUBLIC` grant/CREATE không an toàn hoặc consumer scoped-table chưa review | `PASS` (static/offline) | `test_security_migration_has_rls_invoker_views_and_column_grants`, `test_security_migration_fails_closed_on_public_grants_and_existing_consumers` |
| Views và PII | `analytics.sales/offers/repairs` dùng `security_invoker`; column grants loại address/zip/client/description | `PASS` (static/offline) | `test_security_migration_contains_no_secret_or_source_dml` |
| Không đổi dữ liệu nguồn | Migration không có INSERT/UPDATE/DELETE/TRUNCATE; chỉ ALTER RLS/policy/grant/view/role metadata | `PASS` (static) | cùng static regression; Alembic offline SQL |
| Direct/view CA-TX và totals | Test thật đã định nghĩa cho totals sales/offers/repairs và kiểm không lộ state khác | `BLOCKED` | thiếu `READER_ALL_TEST_DATABASE_URL`, `READER_CA_TEST_DATABASE_URL`, `READER_TX_TEST_DATABASE_URL`; integration skip |
| Least privilege/cross-role | Test thật kiểm superuser/BYPASSRLS/CREATE/owner, effective column/mutation privilege, PII, mutation/DDL và `SET ROLE` chéo; denial phải có SQLSTATE `42501`, INSERT probe dùng FK hợp lệ | `BLOCKED` | cùng ba reader credentials trên DB test đã restore |

Kết quả full backend sau hardening/review P1-T03: 28 pass, 11 skip có blocker. Alembic offline exit 0, gồm 4 lệnh enable RLS, 12 policy và 3 view `security_invoker`; không lộ DSN secret. Runbook yêu cầu rehearsal trên cluster PostgreSQL tách biệt vì role là cluster-wide; migration-cycle test khôi phục reader membership sau upgrade cuối. Kết luận P1-T03: **BLOCKED**. Không đánh dấu task hoàn tất; static/offline evidence không thay thế kiểm tra bằng login role PostgreSQL thật.

### 3.4. P1-T04 — auth, session, RBAC và demo users

| Kiểm tra | Actual | Trạng thái | Bằng chứng/blocker |
|---|---|---|---|
| Password/session primitives | Argon2id; token ngẫu nhiên opaque, DB chỉ lưu SHA-256; expiry cấu hình | `PASS` (unit) | `test_argon2_password_and_opaque_session_token` |
| Cookie và CSRF/Origin | Cookie HttpOnly/SameSite=Lax, Secure ở production; login/logout yêu cầu đúng một header Origin khớp trusted origin; validation error bỏ `input`/`ctx` để không echo password/token | `PASS` (unit/static), live còn blocked | unit origin + sanitized HTTP validation tests; `test_auth.py` đã định nghĩa lifecycle thật |
| Identity/RBAC/ownership | `/me` đọc user/role/profile từ session DB; Viewer bị builder dependency từ chối; ownership query gắn server user ID và trả 404 khi không sở hữu | `PASS` (unit/static), DB còn blocked | `test_origin_and_builder_role_are_server_side_guards`; auth dependencies |
| Fixation/expiry/revocation | Login revoke token cookie cũ và cấp token mới; session hết hạn/logout bị từ chối | `BLOCKED` | thiếu `AUTH_TEST_DATABASE_URL`; PostgreSQL integration skip |
| Seed bốn account | Builder ALL, Viewer ALL, Viewer CA, Builder TX; password chỉ từ SecretStr environment; chạy lặp update cùng username, khóa row và revoke session cũ cùng transaction | `BLOCKED` | script/static test có; chưa chạy bằng runtime role trên DB test |
| Frontend login/user state | Trang `/login` gọi same-origin API, không nhận role/scope từ form; trang chính tải `/me`, hiển thị username/role/scope và có logout | `PASS` (build) | frontend lint, typecheck và production build exit 0 |

Kết quả full backend sau security review P1-T04: 32 pass, 13 skip có blocker. Frontend lint/typecheck/build đều exit 0 khi cấp `BACKEND_URL` hợp lệ. Login và seed cùng dùng row lock để credential reset không thể đua với session issuance. Kết luận P1-T04: **BLOCKED**; không đánh dấu task hoàn tất cho tới khi auth lifecycle, concurrency và seed idempotency chạy bằng runtime credential trên DB test.

## 4. Gate dữ liệu và KPI

| Kiểm tra | Expected | Actual | Trạng thái | Bằng chứng |
|---|---|---|---|---|
| DB thật chạy trong transaction read-only | `transaction_read_only=on` | Server nhận TCP; thiếu credential nên chưa mở transaction | `BLOCKED` | `pg_isready -h localhost -p 5432`; `python backend/scripts/audit_db.py --require-db` → exit 2 |
| 16 bảng / 16 PK / 16 FK | Khớp DB thật và import hoặc ghi rõ diff | Import: 16/16/16; DB: chưa xác minh | `BLOCKED` | `python backend/scripts/audit_db.py`; [data-audit.md](data-audit.md) |
| Duplicate/FK orphan | Báo số cụ thể | Import: PK duplicate 0, UNIQUE duplicate 0, FK orphan 0; DB: chưa xác minh | `BLOCKED` | `python backend/scripts/audit_db.py`; [data-audit.md](data-audit.md) |
| ALL transaction baseline | count 1.000; value 870.798.679,64 theo import | Import khớp; DB chưa xác minh | `BLOCKED` | [data-audit.md](data-audit.md) |
| CA transaction baseline | count 135; value 107.064.313,73 theo import | Import khớp; DB chưa xác minh | `BLOCKED` | [data-audit.md](data-audit.md) |
| TX transaction baseline | count 132; value 128.635.636,80 theo import | Import khớp; DB chưa xác minh | `BLOCKED` | [data-audit.md](data-audit.md) |
| `sold_property_count` | `COUNT(DISTINCT property_id)`, không phải transaction count | Import: ALL 125 distinct / 1.000 transactions; DB chưa chạy | `BLOCKED` | `backend/tests/test_golden_fixtures.py` pass; live DB blocked |
| `accepted_offer_rate` | accepted / tất cả offers cùng tập; mẫu số 0 → no data | Import: 35/125; empty = null/no_data; DB chưa chạy | `BLOCKED` | `backend/tests/test_golden_fixtures.py` pass; live DB blocked |
| `repair_cost` | SUM một fact theo `repair_date` | Import: 2.993.224,70; empty = null/no_data; DB chưa chạy | `BLOCKED` | `backend/tests/test_golden_fixtures.py` pass; live DB blocked |
| Không fan-out | Không query nào SUM sau join nhiều fact/many-to-many | 6 prepared queries đều chỉ dùng một fact; DB chưa chạy | `BLOCKED` | static fixture test pass; live DB blocked |
| Ngày biên/kỳ rỗng | Inclusive start, exclusive end; empty contract đúng | 6 ngày biên + ALL/CA/TX kỳ rỗng pass trên import | `BLOCKED` | `backend/tests/test_golden_fixtures.py` pass; live DB blocked |

Nguồn chuẩn ban đầu: `docs/kpi-catalog.md`, `backend/tests/fixtures/golden_queries.sql`, `backend/tests/fixtures/golden_results.json`. Hiện baseline DB thật còn `BLOCKED` nếu chưa có credential chỉ đọc.

P0-T02 provisional validation: `python -m pytest -q` trong `backend/` đạt 5/5 test trên file import. Task vẫn `BLOCKED` ở mức baseline cuối vì chưa thể chạy chính các prepared PostgreSQL query trên DB thật và đối chiếu sai lệch DB–import.

## 5. Đánh giá Agent — 30 yêu cầu tiếng Việt

Nguồn: `backend/tests/evaluation/prompts.json`.

### 5.1. Coverage bắt buộc

| Nhóm | Số case | IDs | Kết quả |
|---|---:|---|---|
| Hợp lệ | 20 | `valid_001`–`valid_020` | `NOT_RUN` |
| Mơ hồ | 5 | `ambiguous_001`–`ambiguous_005` | `NOT_RUN` |
| Không hỗ trợ | 5 | `unsupported_001`–`unsupported_005` | `NOT_RUN` |
| Phase 2 | 23 | `valid_001`–`valid_014`; `ambiguous_001`–`ambiguous_003`, `ambiguous_005`; `unsupported_001`–`unsupported_005` | `NOT_RUN` |
| Phase 4, phải đánh giá lại | 7 | `valid_015`–`valid_020`; `ambiguous_004` | `NOT_RUN` |

Validation fixture P0-T03: **PASS** — `python -m pytest -q` trong `backend/` kiểm tra schema/coverage/semantic consistency và toàn bộ suite đạt 10/10 test ngày 12/10/2026. Đây chỉ là nghiệm thu corpus/oracle; chưa case Agent nào được chạy nên các dòng kết quả bên trên vẫn `NOT_RUN`.

Phase 3 phải báo riêng pre-check phase 2 gồm 14 valid, 4 ambiguous và 5 unsupported; không tính 7 case phase 4 chưa triển khai là pass/fail LLM. Vì phase 2 chỉ có 14 valid, pre-check này **không thể** chứng minh ngưỡng 18/20 và không phải release gate. Tại Phase 4 chạy lại đủ 20 valid, 5 ambiguous, 5 unsupported; ngưỡng valid là ít nhất 18/20.

### 5.2. Cách chấm một case

Một case hợp lệ chỉ pass khi đồng thời đúng:

1. `outcome=plan`, toàn bộ KPI ID thuộc catalog/version mong đợi.
2. Dimension hợp lệ cho từng fact; ngày dùng đúng date field.
3. Filter, nửa khoảng ngày, sort, limit và chart khớp oracle.
4. Scope bằng giao của request với profile server; không mở rộng quyền.
5. Mixed-fact dashboard tạo query riêng, không join fact.
6. SQL thực thi cho kết quả khớp golden Decimal/tỷ lệ/grain.

Case mơ hồ chỉ pass khi trả `clarification`, hỏi đủ nội dung oracle và không query. Case không hỗ trợ chỉ pass khi từ chối đúng reason, không query và không bịa KPI. Authorization denial phải xảy ra trước Agent/DB.

Mỗi case phải lưu `case_id`, mode, provider/model/config, actual outcome, plan diff, SQL/result nếu áp dụng, scope/auth, latency, trạng thái và artifact. Chỉ `PASS` khi tất cả điều kiện của case cùng đạt; `BLOCKED`, `NOT_RUN` hoặc `SKIPPED` không được cộng vào số pass. Báo cáo mock và live tách riêng; mock không thay bằng chứng live.

### 5.3. Kết quả tổng hợp

| Chế độ | Provider/model/config | Valid đúng / tổng | Ambiguous đúng / 5 | Unsupported đúng / 5 | SQL/result đúng | Tokens | Chi phí ước tính | Trạng thái |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Mock | `<config>` | `<n>/<d>` | `<n>/5` | `<n>/5` | `<n>/<d>` | `<n>` | N/A | `NOT_RUN` |
| Live | `<provider/model>` | `<n>/<d>` | `<n>/5` | `<n>/5` | `<n>/<d>` | `<n>` | `<amount>` | `NOT_RUN` |

### 5.4. Chi tiết từng case

| Case ID | Phase | Expected outcome | Actual outcome | Plan diff | SQL/result | Scope/auth | Latency | Trạng thái | Artifact |
|---|---|---|---|---|---|---|---:|---|---|
| `<id>` | `<2/4>` | `<oracle>` | `<actual>` | `<diff>` | `<result>` | `<result>` | `<ms>` | `NOT_RUN` | `<path>` |

## 6. Ma trận quyền và bảo mật

| Kịch bản | Expected | Actual | Trạng thái | Bằng chứng |
|---|---|---|---|---|
| Builder ALL tạo/chỉnh/duyệt dashboard mình sở hữu | Cho phép | `<actual>` | `NOT_RUN` | `<test>` |
| Viewer gọi create/message/approval | 403 trước Agent/query | `<actual>` | `NOT_RUN` | `<test>` |
| Builder khác owner đọc draft/checkpoint/approve | 403/404, không lộ tồn tại nhạy cảm | `<actual>` | `NOT_RUN` | `<test>` |
| Viewer CA mở dashboard đã duyệt | Chỉ dữ liệu CA | `<actual>` | `NOT_RUN` | `<test>` |
| Viewer CA yêu cầu TX | Empty/no data, không tự mở rộng ALL | `<actual>` | `NOT_RUN` | `<test>` |
| Reader CA/TX SELECT trực tiếp và qua view | Chỉ đúng bang | `<actual>` | `NOT_RUN` | `<RLS test>` |
| Reader INSERT/UPDATE/DELETE/DDL | Bị từ chối | `<actual>` | `NOT_RUN` | `<RLS test>` |
| Reader đọc PII | Bị từ chối | `<actual>` | `NOT_RUN` | `<grant test>` |
| Prompt yêu cầu đổi scope/bỏ validation/arbitrary SQL | Bị từ chối; không query | `<actual>` | `NOT_RUN` | `<adversarial test>` |
| CSRF/Origin không hợp lệ | Mutation bị chặn | `<actual>` | `NOT_RUN` | `<auth test>` |

## 7. HITL, phiên bản và phục hồi

| Kịch bản | Expected | Actual | Trạng thái | Bằng chứng |
|---|---|---|---|---|
| Preview thành công | Chỉ tạo draft `awaiting_approval`; Viewer chưa thấy | `<actual>` | `NOT_RUN` | `<test>` |
| Reject | Kết thúc lượt, không publish | `<actual>` | `NOT_RUN` | `<test>` |
| Approve đúng revision/hash/base version | Tạo đúng một version chính thức | `<actual>` | `NOT_RUN` | `<test>` |
| Stale draft/base version | HTTP 409 | `<actual>` | `NOT_RUN` | `<test>` |
| Double click/retry approval | Idempotent, một version | `<actual>` | `NOT_RUN` | `<test>` |
| Mất response sau commit rồi retry | Trả cùng kết quả, không duplicate | `<actual>` | `NOT_RUN` | `<test>` |
| Restart khi `awaiting_approval` | Khôi phục đúng conversation/draft | `<actual>` | `NOT_RUN` | `<test>` |
| Edit dashboard đã duyệt | Viewer thấy bản cũ đến lần approve mới | `<actual>` | `NOT_RUN` | `<test>` |
| Năm lượt edit liên tiếp | Giữ ID/widget không liên quan; filter tính lại | `<actual>` | `NOT_RUN` | `<test>` |

## 8. Lỗi, giới hạn và khả năng phục hồi

| Kịch bản | Expected | Actual | Trạng thái |
|---|---|---|---|
| LLM 429/timeout | Lỗi có cấu trúc; không ghi đè bản duyệt | `<actual>` | `NOT_RUN` |
| Structured output sai | Tối đa một vòng sửa; tính vào budget | `<actual>` | `NOT_RUN` |
| KPI/dimension không hỗ trợ | Clarification/refusal, không query | `<actual>` | `NOT_RUN` |
| DB timeout 5 giây | Lỗi có cấu trúc | `<actual>` | `NOT_RUN` |
| Query >1.000 dòng | Yêu cầu giảm chi tiết, không âm thầm truncate | `<actual>` | `NOT_RUN` |
| Một widget lỗi | Widget báo lỗi, trang còn hoạt động | `<actual>` | `NOT_RUN` |
| Session hết hạn | Bị chặn, không lộ draft/data | `<actual>` | `NOT_RUN` |
| Kỳ/scope rỗng | Trạng thái no data, không mở rộng scope | `<actual>` | `NOT_RUN` |

## 9. UI và end-to-end

| Kiểm tra | Expected | Actual | Trạng thái | Artifact |
|---|---|---|---|---|
| Dashboard card/line/bar/horizontal/pie/donut/table | Render đúng dữ liệu/schema | `<actual>` | `NOT_RUN` | `<screenshot/test>` |
| Loading/empty/error từng widget | Không phá toàn trang | `<actual>` | `NOT_RUN` | `<artifact>` |
| Resize/viewport | Chart resize đúng | `<actual>` | `NOT_RUN` | `<artifact>` |
| Nhãn dài/HTML | Hiển thị text, không eval | `<actual>` | `NOT_RUN` | `<artifact>` |
| Filter ngày/bang/loại | Số liệu tính lại đúng scope | `<actual>` | `NOT_RUN` | `<artifact>` |
| Viewer UI | Không có nút Agent/approve | `<actual>` | `NOT_RUN` | `<artifact>` |

## 10. Ngân sách và hiệu năng

| Metric/gate | Ngưỡng | Số mẫu | Actual | Error rate | Trạng thái |
|---|---:|---:|---:|---:|---|
| LLM calls/lượt | ≤3, gồm retry | `<n>` | `<actual>` | `<rate>` | `NOT_RUN` |
| Token/lượt | ≤24.000 | `<n>` | `<actual>` | `<rate>` | `NOT_RUN` |
| LLM time/lượt | ≤60 giây | `<n>` | `<actual>` | `<rate>` | `NOT_RUN` |
| Chi phí/lượt | ≤0,10 USD | `<n>` | `<actual>` | `<rate>` | `NOT_RUN` |
| Chi phí/ngày/Builder | ≤1 USD | `<n>` | `<actual>` | `<rate>` | `NOT_RUN` |
| Dashboard đã lưu P95 | <3 giây | ≥30 | `<actual>` | `<rate>` | `NOT_RUN` |
| Tạo AI P95 | <45 giây | ≥30 | `<actual>` | `<rate>` | `NOT_RUN` |

Ghi riêng warm-up, DB/LLM/render latency, model/config/dataset và concurrency. EXPLAIN cost không được báo như thời gian hoặc tiền.

## 11. Checklist demo nghiệm thu cuối

| Bước | Kịch bản | Expected | Actual | Trạng thái | Artifact |
|---:|---|---|---|---|---|
| 1 | Builder ALL tạo “giá trị giao dịch năm 2025 theo tháng, bang và loại bất động sản” | Khớp `valid_001` | `<actual>` | `NOT_RUN` | `<artifact>` |
| 2 | Kiểm tra ba KPI card, ba chart, nguồn KPI/SQL/kỳ | Đúng catalog/golden | `<actual>` | `NOT_RUN` | `<artifact>` |
| 3 | Năm edit: CA; cột ngang; thêm sold properties; bỏ widget; đổi kỳ | Diff đúng, widget khác giữ nguyên | `<actual>` | `NOT_RUN` | `<artifact>` |
| 4 | Restart backend lúc chờ duyệt | Khôi phục đúng draft | `<actual>` | `NOT_RUN` | `<artifact>` |
| 5 | Approve rồi retry cùng approval | Chỉ một version | `<actual>` | `NOT_RUN` | `<artifact>` |
| 6 | Viewer CA mở/filter, thử TX | CA đúng; TX no data | `<actual>` | `NOT_RUN` | `<artifact>` |
| 7 | Viewer mutation; tài khoản khác lấy draft | Đều bị chặn | `<actual>` | `NOT_RUN` | `<artifact>` |
| 8 | Builder sửa bản đã lưu | Viewer thấy bản cũ tới approve mới | `<actual>` | `NOT_RUN` | `<artifact>` |

## 12. Blocker, sai lệch và giới hạn

| ID | Mức độ | Mô tả | Ảnh hưởng gate | Owner | Hành động/điều kiện gỡ | Trạng thái |
|---|---|---|---|---|---|---|
| `P0-T01-DB-CREDENTIAL` | Cao | PostgreSQL nhận kết nối tại localhost:5432 nhưng không có credential/DSN chỉ đọc | Xác minh DB thật, diff DB-import và hoàn tất P0-T01 | Chủ môi trường DB | Cấp `AUDIT_DATABASE_URL` cho role chỉ đọc rồi chạy `python backend/scripts/audit_db.py --require-db` | `open` |
| `P1-T02-MIGRATION-TEST` | Cao | Chưa có DB test đã restore, migration credential và runtime credential tách biệt | Upgrade/downgrade, bảo toàn nguồn, restore và least privilege | Chủ môi trường DB | Cấp ba biến test theo README, restore backup vào DB có tên chứa `test`, chạy integration suite | `open` |
| `P1-T03-READER-CREDENTIALS` | Cao | Chưa có ba login reader ALL/CA/TX trên DB test đã restore | Chưa xác minh RLS, security-invoker view, PII/DDL denial và chống đổi scope bằng PostgreSQL thật | Chủ môi trường DB | Cấp ba `READER_*_TEST_DATABASE_URL` theo `docs/local-runbook.md`, mỗi login chỉ thuộc đúng một reader group, rồi chạy `test_rls.py` | `open` |
| `P1-T04-AUTH-TEST` | Cao | Chưa có runtime credential trên DB test đã migrate | Chưa chạy lifecycle login/fixation/expiry/logout và seed lặp bằng PostgreSQL thật | Chủ môi trường DB | Cấp `AUTH_TEST_DATABASE_URL`, chạy `test_auth.py`, sau đó chạy seed hai lần với bốn password environment và xác minh chỉ bốn username | `open` |

Blocker đã biết tại thời điểm tạo template: chưa có credential read-only để xác minh DB thật; chưa được phép coi baseline import là baseline DB.

## 13. Kết luận và ký xác nhận

| Vai trò | Tên | Kết luận | Ngày | Ghi chú |
|---|---|---|---|---|
| Kỹ thuật | `<name>` | `<PASS/FAIL/BLOCKED>` | `<date>` | `<notes>` |
| Nghiệp vụ | `<name>` | `<accepted/rejected>` | `<date>` | `<notes>` |

Kết luận tổng: `<NOT_RUN/PASS/FAIL/BLOCKED>`. Chỉ đánh dấu MVP hoàn tất khi mọi gate bắt buộc có bằng chứng và không còn blocker bắt buộc.
