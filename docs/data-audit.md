# Khảo sát dữ liệu — P0-T01

## Trạng thái và phạm vi bằng chứng

Thời điểm chạy lại: **2026-10-12 10:21:39 UTC** (17:21:39 Asia/Ho_Chi_Minh). Môi trường: Windows, Python 3.11, workspace `D:/AI-Dashboard-Agent`.

| Nguồn bằng chứng | Trạng thái | Kết luận được phép |
|---|---|---|
| File import `data/real-estate-sales-sample-database-v3-sql-postgres.sql` | Đã khảo sát đầy đủ, chỉ đọc | Các số liệu trong mục “Kết quả file import” |
| PostgreSQL đang chạy | **Bị chặn** | Chưa xác minh version, database, schema thực tế, row count, index, privilege hoặc chênh lệch so với import |

Blocker cụ thể: PostgreSQL tại `localhost:5432` trả trạng thái `accepting connections`, nhưng không có `AUDIT_DATABASE_URL`, `DATABASE_URL`, biến `DB_*`/`PG*`, PG service hoặc `pgpass.conf`; workspace cũng không có file cấu hình credential DB. Không đoán/thử mật khẩu mặc định và không ghi DSN/secret vào log. Thông tin PostgreSQL 16.9 và database `real_estate_db` trong kế hoạch vẫn là thông tin chưa xác minh bằng phiên đăng nhập.

P0-T01 **chưa đạt gate kiểm tra DB thật** cho tới khi chạy script bằng credential chỉ đọc. Phần khảo sát file import đã hoàn tất và không thay đổi file nguồn hay database.

## Cách tái lập

Khảo sát file import, không cần package ngoài:

```powershell
python backend/scripts/audit_db.py
```

Khảo sát đồng thời DB thật (cần `psycopg` 3 và credential chỉ đọc):

```powershell
$env:AUDIT_DATABASE_URL = '<dsn-read-only>'
python backend/scripts/audit_db.py --require-db
```

Script mở kết nối live bằng `BEGIN READ ONLY`, bắt buộc `transaction_read_only=on`, đặt timeout kết nối 5 giây, chỉ chạy `SELECT`/catalog queries, rollback rồi đóng kết nối. Output không chứa DSN, giá trị dữ liệu hay tên role/owner nguyên văn (chỉ fingerprint 12 ký tự). Audit live kiểm kê direct/effective table privileges, quyền schema, owner fingerprint, RLS, PK/FK/UNIQUE/index và so sánh constraint/schema/count/baseline với import. `--require-db` trả exit code 2 khi thiếu DSN hoặc audit live lỗi.

## Kết quả file import

### Định danh nguồn

- Kích thước: 140.909 byte.
- SHA-256: `c585831fc15942bfa3f3fa793d4d4ebedfde81905ae1214781431001043abbe3`.
- Header tự mô tả dữ liệu synthetic, deterministic, CC0-1.0, seed `flagship:real-estate-sales-sample-database:1k`.
- Schema không được ghi tường minh; khi chạy với `search_path` mặc định, 16 bảng được tạo trong `public`.
- File bọc thao tác trong `BEGIN`/`COMMIT`. Audit chỉ phân tích file, không thực thi import.

### Schema, khóa và index

- 16 bảng; mỗi bảng có đúng một primary key một cột: 16 PK.
- 16 foreign key; đầy đủ trong [data-dictionary.md](data-dictionary.md).
- 5 ràng buộc `UNIQUE`: `agents.license_number`, `appraisers.license_number`, `inspectors.license_number`, `payment_methods.method_name`, `property_types.type_name`.
- Không có câu lệnh `CREATE INDEX` tường minh. Nếu import được chạy trên PostgreSQL, 16 PK và 5 `UNIQUE` sẽ tạo 21 index hỗ trợ constraint; đây là hành vi dự kiến từ DDL, **không phải inventory index của DB thật**.
- File không có `GRANT`/`REVOKE`; privilege và thuộc tính role thực tế chưa thể xác minh.

### Số dòng, NULL và khoảng ngày

| Bảng | Dòng | NULL | Khoảng ngày/timestamp trong file |
|---|---:|---:|---|
| `agencies` | 16 | 0 | — |
| `agents` | 125 | 0 | — |
| `agent_agencies` | 125 | 70 | `start_date`: 2021-01-05 → 2025-12-25; `end_date`: 2022-07-13 → 2029-04-03 |
| `appraisers` | 16 | 0 | — |
| `clients` | 125 | 0 | `created_at`: 2023-01-04 16:15:40 → 2025-12-01 15:12:31 |
| `inspectors` | 16 | 0 | — |
| `neighbourhoods` | 16 | 0 | — |
| `payment_methods` | 6 | 0 | — |
| `property_types` | 8 | 0 | — |
| `properties` | 125 | 0 | `created_at`: 2021-01-28 14:10:29 → 2025-12-14 11:44:29 |
| `appraisals` | 125 | 0 | `appraisal_date`: 2021-02-20 → 2025-12-14 |
| `inspections` | 125 | 0 | `inspection_date`: 2021-02-08 → 2025-12-07 |
| `offers` | 125 | 0 | `offer_date`: 2021-02-23 → 2026-03-25 |
| `property_neighbourhoods` | 125 | 0 | `assigned_date`: 2023-01-13 → 2025-12-12 |
| `repairs` | 125 | 0 | `repair_date`: 2021-02-24 → 2026-08-04 |
| `transactions` | 1.000 | 0 | `transaction_date`: 2021-02-12 → 2026-07-13 |

70 giá trị NULL đều nằm ở `agent_agencies.end_date`, cột duy nhất được khai báo nullable. Các cột còn lại không có NULL trong import.

### Duplicate và FK orphan

- Duplicate primary key: 0 trên cả 16 bảng.
- Duplicate trên 5 khóa `UNIQUE`: 0.
- FK orphan: 0 trên cả 16 quan hệ FK.
- Audit đếm duplicate/orphan trên các tuple đã parse; không xuất giá trị nhận dạng hoặc PII.

### Baseline giao dịch từ file

Các tổng sau dùng `transactions` làm grain, nối đúng một lần đến `properties` qua `property_id` để lọc `state`; tiền giữ bằng `Decimal`, không làm tròn trung gian.

| Scope | Giao dịch | Bất động sản khác nhau | Tổng `sale_price` |
|---|---:|---:|---:|
| ALL | 1.000 | 125 | 870.798.679,64 |
| CA | 135 | 22 | 107.064.313,73 |
| TX | 132 | 14 | 128.635.636,80 |

Các số này khớp baseline import trong kế hoạch. Đơn vị tiền tệ chưa được dataset xác nhận; không gán nhãn USD.

## Quan hệ nhiều-nhiều và fan-out

### Lịch sử môi giới–đại lý

`agent_agencies` có 125 dòng nhưng chỉ 64 `agent_id` khác nhau. Với điều kiện ngày:

```sql
aa.agent_id = t.agent_id
AND aa.start_date <= t.transaction_date
AND (aa.end_date IS NULL OR t.transaction_date <= aa.end_date)
```

- 631/1.000 giao dịch không khớp đại lý nào.
- 200/1.000 giao dịch khớp nhiều hơn một đại lý.
- Chỉ 169 giao dịch khớp đúng một đại lý.
- Một giao dịch có thể khớp tối đa 9 dòng lịch sử trong file.

Vì vậy không dùng join này để tính KPI cộng gộp hoặc phân tích theo đại lý ở MVP.

### Bất động sản–khu dân cư

`property_neighbourhoods` có 125 dòng cho 70 bất động sản khác nhau. Có 30 bất động sản mang nhiều hơn một liên kết, tạo thêm 55 dòng so với grain một dòng/bất động sản; tối đa 10 liên kết cho một bất động sản. Join trực tiếp với transaction có thể nhân bản fact. MVP dùng `properties.state` và `properties.city`, không dùng neighbourhood làm dimension KPI.

## So sánh DB thật với file import

Chưa có dữ kiện DB thật để so sánh. Không có chênh lệch nào được tuyên bố là “0”. Khi có credential, output live của script sẽ ghi riêng:

- PostgreSQL version, database, fingerprint của current user, `rolsuper`/`rolbypassrls`, và xác nhận transaction read-only;
- columns, PK, FK, index và privilege hiện hành;
- row count, NULL, khoảng ngày, duplicate PK/unique và FK orphan;
- baseline ALL/CA/TX, hai phép kiểm tra fan-out;
- `row_count_differences` và `baseline_differences` so với chính file import có hash ở trên.

Nếu DB khác import, baseline DB phải được ghi nhận riêng; không sửa dữ liệu để ép khớp.

## Baseline KPI P0-T02 từ file import

Bảy KPI đã được định nghĩa tại [kpi-catalog.md](kpi-catalog.md). Đây vẫn là **baseline file import**, không được gọi là kết quả DB thật. Ba fact được tính bằng ba phép tổng hợp độc lập; không query nào join `transactions`, `offers` và `repairs` với nhau.

| Scope | `sales_value` | `transaction_count` | `average_sale_value` | `sold_property_count` | `offer_count` | `accepted_offer_rate` | `repair_cost` |
|---|---:|---:|---:|---:|---:|---:|---:|
| ALL | 870.798.679,64 | 1.000 | 870.798,67964 | 125 | 125 | 35/125 = 0,28 | 2.993.224,70 |
| CA | 107.064.313,73 | 135 | 107.064.313,73 / 135 | 22 | 14 | 5/14 | 385.283,39 |
| TX | 128.635.636,80 | 132 | 974.512,40 | 14 | 11 | 2/11 | 456.693,59 |

Phân số được giữ ở bảng khi biểu diễn thập phân là vô hạn. Giá trị Decimal đầy đủ, tử số/mẫu số, kỳ 2025, kỳ rỗng và từng ngày biên nằm trong `backend/tests/fixtures/golden_results.json`. Các kiểm tra biên xác nhận ngày nhỏ nhất/lớn nhất của từng fact đều được lấy khi dùng khoảng ngày nửa mở.

Lần validation P0-T02 ngày 12/10/2026 chạy `python -m pytest -q` trong `backend/`: 5 test pass. Test tính lại oracle trực tiếp từ tuple của file import, kiểm tra đủ ALL/CA/TX cho toàn thời gian, năm 2025 và kỳ rỗng 2030; kiểm tra sáu ngày biên, Decimal đến `0.01`, fraction trung bình/tỷ lệ, và kiểm tra tĩnh mỗi prepared SQL chỉ tham chiếu một fact. Đây không phải bằng chứng thực thi SQL trên DB live.

`sold_property_count` khác rõ `transaction_count` (ALL: 125 so với 1.000), chứng minh phải dùng `COUNT(DISTINCT property_id)`. Mẫu số tỷ lệ accepted là toàn bộ offer trong tập lọc: ALL 125, CA 14, TX 11; không chỉ accepted + rejected. Khi kỳ rỗng, count là 0 còn sum/trung bình/tỷ lệ là `null` và trạng thái `no_data`.

## Hạn chế và quyết định cho task sau

- Bản dự thảo catalog P0-T02 đã được kiểm chứng theo file import; baseline DB thật vẫn chưa thể chốt cho tới khi có credential chỉ đọc.
- Các trường `email`, `phone`, tên người và địa chỉ là PII/nhạy cảm; lớp analytics sau này không được cấp các cột không cần thiết.
- Các timestamp trong file không kèm múi giờ. Không suy diễn timezone.
- Chưa xác minh owner, consumers, RLS, grants hoặc index vật lý của DB đang chạy; không triển khai migration/RLS trong P0-T01.

## Trạng thái triển khai bảo mật analytics P1-T03

Migration `0002_analytics_security` đã được chuẩn bị với RLS cho `properties`, `transactions`, `offers`, `repairs`, column-level grants không gồm PII, và ba view `security_invoker`. Migration có guard từ chối ghi đè cấu hình RLS/tên reader role, từ chối `PUBLIC` grant/CREATE không an toàn và consumer cũ chưa review trước khi bật default-deny; migration không chứa DML nguồn. Reader pool kiểm principal và effective privileges khi kết nối. Đây chưa phải bằng chứng DB thật: chưa có ba reader credential trên DB test đã restore, nên totals CA/TX, quyền trực tiếp/qua view và chống đổi role vẫn `BLOCKED`.

