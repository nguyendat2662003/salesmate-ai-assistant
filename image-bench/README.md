# image-bench/ — benchmark cục bộ: gpt-image-1-mini vs Seedream 4.0

Công cụ RIÊNG để đo, **không phải một phần sản phẩm SalesMate**. Không import
`src/` lẫn `interface/backend/` — chỉ gọi thẳng hai API bằng đúng hình dạng
request mà `interface/backend/app/services/image_edit.py` đã dùng (và đã có
test), để số đo phản ánh đúng cái sản phẩm thật đang chạy.

## Đo cái gì, không đo cái gì

| | |
|---|---|
| **Tự động đo** | Latency (đồng hồ quanh đúng lệnh gọi HTTP của từng model) và cost mỗi ảnh |
| **Bạn tự chấm** | 3 tiêu chí, mỗi tiêu chí 1-5 sao + ghi chú, ngay trên UI sau khi xem ảnh |

Ba tiêu chí (khai ở `TIEU_CHI` trong `server.py`, UI đọc qua `/api/tieu-chi` —
sửa tên tiêu chí chỉ cần sửa một chỗ):

1. **Đúng thao tác** — add/remove/change đúng vật khách yêu cầu.
2. **Giữ nguyên phần còn lại** — phần ảnh không liên quan đến yêu cầu có bị đổi theo không.
3. **Chất lượng ảnh vùng sửa** — vùng vừa sửa có artifact/méo/lem không.

Không có rubric tự động cho chất lượng ảnh — công cụ này chỉ ghi lại điểm bạn
chấm, không tự kết luận "ảnh nào tốt hơn". Bảng lịch sử tính sẵn cột **TB**
(trung bình cộng 3 tiêu chí) để so sánh nhanh, số liệu thật vẫn nằm ở 3 cột
điểm riêng.

## Cài đặt & chạy

```bash
pip install fastapi uvicorn httpx python-multipart python-dotenv
python image-bench/server.py
```

Mở **http://127.0.0.1:8010**.

### Cần trong `.env` ở gốc repo

```
OPENAI_API_KEY=...      # đã có sẵn — dùng lại key của lõi AI
ARK_API_KEY=...         # BytePlus ModelArk — https://console.byteplus.com/ark
                        # CHƯA có trong .env hiện tại của máy này, cần thêm
```

Tuỳ chọn (mặc định lấy đúng model production đang dùng, xem
`interface/backend/.env.example`):

```
OPENAI_IMAGE_MODEL=gpt-image-1-mini
OPENAI_IMAGE_SIZE=auto
SEEDREAM_MODEL=seedream-4-0-250828
SEEDREAM_SIZE=2K
SEEDREAM_WATERMARK=false
```

Thiếu key nào thì lượt gọi model đó trả lỗi rõ ràng ("Thiếu ARK_API_KEY…"),
model còn lại vẫn chạy — không rớt cả lượt so sánh.

## Giá dùng để tính cost — có nguồn, không phải số đoán

| Model | Cách tính | Nguồn |
|---|---|---|
| `gpt-image-1-mini` | Theo token thật trong `usage` của response: text input $2,00 / 1M · image input $2,50 / 1M · image output $8,00 / 1M | [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) |
| `seedream-4-0-250828` | Phẳng $0,03 / ảnh, không đổi theo resolution | [docs.byteplus.com/en/docs/ModelArk/1824718](https://docs.byteplus.com/en/docs/ModelArk/1824718) |

Nếu response OpenAI không trả `input_tokens_details` (breakdown text/ảnh), cost
được đánh dấu **ước tính** (`cost_uoc_tinh: true`, hiện chữ "~$" trên UI) — coi
hết input là ảnh (giá cao hơn text) để không báo cost thấp hơn thực tế.

## Dữ liệu ghi lại

- `results/log.jsonl` — mỗi dòng một lượt chạy: thời điểm, prompt, nhãn,
  latency/cost/lỗi từng model, và `danh_gia` (điểm 1-5 + ghi chú bạn nhập trên
  UI, điền sau nếu muốn — xem ảnh xong vài ngày mới chấm cũng được).
- `results/images/` — ảnh gốc + ảnh cả hai model của mọi lượt chạy, đặt tên
  theo `run_id`.

Cả hai đều **không commit vào git** (xem `.gitignore` ở gốc repo) — đây là dữ
liệu chạy tay của bạn, có thể chứa ảnh nội thất thật của căn hộ.

## Vì sao gọi đồng thời (không tuần tự)

`asyncio.gather` gọi cả hai API cùng lúc: đúng ý "so sánh song song", và công
bằng hơn cho latency — hai lượt cùng chờ mạng trong cùng một khoảng thời gian
thay vì lượt sau ăn ké cache DNS/TLS của lượt trước. Mỗi model vẫn có đồng hồ
riêng quanh đúng lệnh `httpx` của nó nên không lượt nào "mượn" thời gian của
lượt kia.
