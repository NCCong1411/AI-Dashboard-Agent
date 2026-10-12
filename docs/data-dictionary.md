# Từ điển dữ liệu nguồn

Nguồn của tài liệu này là file import có SHA-256 `c585831fc15942bfa3f3fa793d4d4ebedfde81905ae1214781431001043abbe3`. Kiểu, nullable và constraint dưới đây là **DDL trong file**, chưa được xác minh trên DB đang chạy. Mọi bảng dùng surrogate integer identity làm primary key.

Quy ước phân loại: **PII** là dữ liệu nhận dạng/liên hệ; **nhạy cảm** là địa chỉ hoặc mã giấy phép; **nghiệp vụ** là dữ liệu được phép cân nhắc cho analytics theo nguyên tắc tối thiểu quyền.

## `agencies` — 16 dòng

| Cột | Kiểu | Null | Constraint / ý nghĩa | Phân loại |
|---|---|---|---|---|
| `agency_id` | integer identity | Không | PK; định danh đại lý | Nghiệp vụ |
| `address` | varchar(101) | Không | Địa chỉ đại lý | Nhạy cảm |
| `agency_name` | varchar(114) | Không | Tên đại lý | Nghiệp vụ |
| `city` | varchar(40) | Không | Thành phố | Nghiệp vụ |
| `phone` | varchar(20) | Không | Điện thoại | PII |
| `state` | varchar(3) | Không | Bang | Nghiệp vụ |
| `zip_code` | varchar(10) | Không | Mã bưu chính | Nghiệp vụ |

## `agents` — 125 dòng

| Cột | Kiểu | Null | Constraint / ý nghĩa | Phân loại |
|---|---|---|---|---|
| `agent_id` | integer identity | Không | PK; định danh môi giới | Nghiệp vụ |
| `email` | varchar(78) | Không | Email | PII |
| `first_name` | varchar(30) | Không | Tên | PII |
| `last_name` | varchar(44) | Không | Họ | PII |
| `license_number` | varchar(10) | Không | UNIQUE; số giấy phép | Nhạy cảm |
| `phone` | varchar(26) | Không | Điện thoại | PII |

## `agent_agencies` — 125 dòng

Lịch sử gán môi giới vào đại lý; có thể có khoảng chồng lấn và không bao phủ ngày giao dịch.

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `agent_agency_id` | integer identity | Không | PK |
| `agency_id` | integer | Không | FK → `agencies.agency_id` |
| `agent_id` | integer | Không | FK → `agents.agent_id` |
| `end_date` | date | Có | Ngày kết thúc, NULL nghĩa là chưa có ngày kết thúc |
| `start_date` | date | Không | Ngày bắt đầu |

## `appraisers` — 16 dòng

| Cột | Kiểu | Null | Constraint / ý nghĩa | Phân loại |
|---|---|---|---|---|
| `appraiser_id` | integer identity | Không | PK | Nghiệp vụ |
| `first_name` | varchar(30) | Không | Tên | PII |
| `last_name` | varchar(44) | Không | Họ | PII |
| `license_number` | varchar(10) | Không | UNIQUE; số giấy phép | Nhạy cảm |

## `clients` — 125 dòng

| Cột | Kiểu | Null | Constraint / ý nghĩa | Phân loại |
|---|---|---|---|---|
| `client_id` | integer identity | Không | PK; định danh khách hàng | Nghiệp vụ |
| `created_at` | timestamp | Không | Thời điểm tạo, không kèm timezone | Nghiệp vụ |
| `email` | varchar(78) | Không | Email | PII |
| `first_name` | varchar(30) | Không | Tên | PII |
| `last_name` | varchar(44) | Không | Họ | PII |
| `phone` | varchar(26) | Không | Điện thoại | PII |

## `inspectors` — 16 dòng

| Cột | Kiểu | Null | Constraint / ý nghĩa | Phân loại |
|---|---|---|---|---|
| `inspector_id` | integer identity | Không | PK | Nghiệp vụ |
| `first_name` | varchar(30) | Không | Tên | PII |
| `last_name` | varchar(44) | Không | Họ | PII |
| `license_number` | varchar(10) | Không | UNIQUE; số giấy phép | Nhạy cảm |

## `neighbourhoods` — 16 dòng

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `neighbourhood_id` | integer identity | Không | PK |
| `city` | varchar(40) | Không | Thành phố |
| `name` | varchar(120) | Không | Tên khu dân cư |
| `state` | varchar(3) | Không | Bang |

## `payment_methods` — 6 dòng

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `payment_method_id` | integer identity | Không | PK |
| `method_name` | varchar(21) | Không | UNIQUE; tên phương thức |

## `property_types` — 8 dòng

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `property_type_id` | integer identity | Không | PK |
| `type_name` | varchar(13) | Không | UNIQUE; tên loại bất động sản |

## `properties` — 125 dòng

| Cột | Kiểu | Null | Constraint / ý nghĩa | Phân loại |
|---|---|---|---|---|
| `property_id` | integer identity | Không | PK | Nghiệp vụ |
| `address` | varchar(101) | Không | Địa chỉ bất động sản | Nhạy cảm |
| `city` | varchar(40) | Không | Thành phố; dimension MVP | Nghiệp vụ |
| `created_at` | timestamp | Không | Thời điểm tạo, không kèm timezone | Nghiệp vụ |
| `price` | numeric(14,2) | Không | Giá thuộc tính của bất động sản; không mặc định là giá bán | Nghiệp vụ |
| `property_type_id` | integer | Không | FK → `property_types.property_type_id` | Nghiệp vụ |
| `state` | varchar(3) | Không | Bang; dimension và scope MVP | Nghiệp vụ |
| `zip_code` | varchar(10) | Không | Mã bưu chính | Nghiệp vụ |

## `appraisals` — 125 dòng

Grain: một dòng thẩm định; file không áp đặt một thẩm định duy nhất cho mỗi bất động sản.

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `appraisal_id` | integer identity | Không | PK |
| `appraisal_date` | date | Không | Ngày thẩm định |
| `appraised_value` | numeric(14,2) | Không | Giá trị thẩm định; đơn vị tiền chưa xác nhận |
| `appraiser_id` | integer | Không | FK → `appraisers.appraiser_id` |
| `property_id` | integer | Không | FK → `properties.property_id` |

## `inspections` — 125 dòng

Grain: một lần kiểm định.

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `inspection_id` | integer identity | Không | PK |
| `inspection_date` | date | Không | Ngày kiểm định |
| `inspector_id` | integer | Không | FK → `inspectors.inspector_id` |
| `property_id` | integer | Không | FK → `properties.property_id` |
| `result` | varchar(17) | Không | Kết quả kiểm định |

## `offers` — 125 dòng

Grain: một đề nghị mua; thời gian nghiệp vụ là `offer_date`.

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `offer_id` | integer identity | Không | PK |
| `client_id` | integer | Không | FK → `clients.client_id` |
| `offer_amount` | numeric(14,2) | Không | Giá trị đề nghị; đơn vị tiền chưa xác nhận |
| `offer_date` | date | Không | Ngày đề nghị |
| `property_id` | integer | Không | FK → `properties.property_id` |
| `status` | varchar(9) | Không | Trạng thái đề nghị |

## `property_neighbourhoods` — 125 dòng

Bảng liên kết nhiều-nhiều. Không join trực tiếp vào fact cộng gộp nếu chưa kiểm soát grain/fan-out.

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `property_neighbourhood_id` | integer identity | Không | PK |
| `assigned_date` | date | Không | Ngày gán |
| `neighbourhood_id` | integer | Không | FK → `neighbourhoods.neighbourhood_id` |
| `property_id` | integer | Không | FK → `properties.property_id` |

## `repairs` — 125 dòng

Grain: một lần sửa chữa; thời gian nghiệp vụ là `repair_date`.

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `repair_id` | integer identity | Không | PK |
| `cost` | numeric(14,2) | Không | Chi phí; đơn vị tiền chưa xác nhận |
| `description` | text | Không | Mô tả sửa chữa |
| `property_id` | integer | Không | FK → `properties.property_id` |
| `repair_date` | date | Không | Ngày sửa chữa |

## `transactions` — 1.000 dòng

Grain: một giao dịch. Đây là fact chính cho KPI sales; thời gian nghiệp vụ là `transaction_date`. Một bất động sản có thể có nhiều giao dịch.

| Cột | Kiểu | Null | Constraint / ý nghĩa |
|---|---|---|---|
| `transaction_id` | integer identity | Không | PK |
| `agent_id` | integer | Không | FK → `agents.agent_id` |
| `client_id` | integer | Không | FK → `clients.client_id` |
| `payment_method_id` | integer | Không | FK → `payment_methods.payment_method_id` |
| `property_id` | integer | Không | FK → `properties.property_id` |
| `sale_price` | numeric(14,2) | Không | Giá trị giao dịch; đơn vị tiền chưa xác nhận |
| `transaction_date` | date | Không | Ngày giao dịch |

## Lớp analytics và phạm vi truy cập P1-T03

Migration dự thảo `0002_analytics_security` tạo ba view `security_invoker` trong schema `analytics`: `sales`, `offers`, `repairs`. View chỉ xuất khóa fact/property, ngày, số đo KPI, `state`, `city`, loại bất động sản và (riêng sales) `agent_id`. Không view nào xuất `address`, `zip_code`, `client_id`, email, điện thoại hoặc `repairs.description`.

RLS được định nghĩa trên `properties`, `transactions`, `offers`, `repairs` cho ba group role `analytics_reader_all`, `analytics_reader_ca`, `analytics_reader_tx`. CA/TX fact policy chỉ nhận dòng có `property_id` trỏ tới `properties.state` tương ứng. Migration fail-closed nếu phát hiện `PUBLIC` privilege hoặc consumer cũ có thể làm rò dữ liệu/bị default-deny; reader connection cũng xác minh scope membership và quyền hiệu lực. Đây là thiết kế/migration đã kiểm tra tĩnh; hành vi trên PostgreSQL thật còn `BLOCKED` cho tới khi chạy integration bằng ba login role trên DB test đã restore ở cluster tách biệt.

## Danh sách 16 foreign key

| Bảng con | Cột | Bảng cha | Cột |
|---|---|---|---|
| `agent_agencies` | `agency_id` | `agencies` | `agency_id` |
| `agent_agencies` | `agent_id` | `agents` | `agent_id` |
| `properties` | `property_type_id` | `property_types` | `property_type_id` |
| `appraisals` | `appraiser_id` | `appraisers` | `appraiser_id` |
| `appraisals` | `property_id` | `properties` | `property_id` |
| `inspections` | `inspector_id` | `inspectors` | `inspector_id` |
| `inspections` | `property_id` | `properties` | `property_id` |
| `offers` | `client_id` | `clients` | `client_id` |
| `offers` | `property_id` | `properties` | `property_id` |
| `property_neighbourhoods` | `neighbourhood_id` | `neighbourhoods` | `neighbourhood_id` |
| `property_neighbourhoods` | `property_id` | `properties` | `property_id` |
| `repairs` | `property_id` | `properties` | `property_id` |
| `transactions` | `agent_id` | `agents` | `agent_id` |
| `transactions` | `client_id` | `clients` | `client_id` |
| `transactions` | `payment_method_id` | `payment_methods` | `payment_method_id` |
| `transactions` | `property_id` | `properties` | `property_id` |

## Grain và đường join an toàn dự kiến

| Fact | Grain | Date | Join dimension trực tiếp |
|---|---|---|---|
| `transactions` | giao dịch | `transaction_date` | `properties`, `agents`, `clients`, `payment_methods` |
| `offers` | đề nghị | `offer_date` | `properties`, `clients` |
| `repairs` | sửa chữa | `repair_date` | `properties` |
| `appraisals` | thẩm định | `appraisal_date` | `properties`, `appraisers` |
| `inspections` | kiểm định | `inspection_date` | `properties`, `inspectors` |

Không join nhiều fact trước khi `SUM`/`COUNT`. `agent_agencies` và `property_neighbourhoods` có fan-out được định lượng trong [data-audit.md](data-audit.md); không xem chúng là đường join KPI an toàn trong MVP.
