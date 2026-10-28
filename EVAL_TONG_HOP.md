# Tổng hợp Eval — SalesMate

> Gộp hai bộ đánh giá độc lập: **AI Agent** (hỏi đáp/tool-use/an toàn — nguồn
> chính `tonghop_20260827-1118_batch4-chot.xlsx`, lượt chạy chốt 29/29 câu) và
> **Modify Object** (so sánh chất lượng sửa ảnh, `image-bench/`). Cập nhật
> 2026-08-31. Số liệu lấy nguyên từ file kết quả đã chạy thật, không suy diễn.

---

## Phần 1 — Eval AI Agent

Nguồn chính: **`tonghop_20260827-1118_batch4-chot.xlsx`** — lượt chạy **chốt**
toàn bộ 29 câu golden dataset (2026-08-27T11:26:25, commit `a84ca6c`, nhãn
`batch4-chot`), chấm bằng rule-based + đối chiếu DB + LLM Judge. Bổ sung từ
[`eval/README.md`](eval/README.md) và [`eval/SalesMate_Eval_Plan.xlsx`](eval/SalesMate_Eval_Plan.xlsx)
cho phần phương pháp luận.

### Phương pháp

- Gọi thẳng lõi AI `:8001/api/v1/chat/stream`, chạy tuần tự (không song song)
  để đo đúng độ trễ hệ thống.
- Ba đường chấm: **rule-based** (regex) · **LLM Judge** (`claude-sonnet-5`,
  rubric 1-5) · **đối chiếu DB / người duyệt** (cấm Judge tự quyết case pháp
  lý, HITL, và mọi câu Judge chấm ≤ 2 điểm — bắt buộc người xem lại, xem mục
  "Cần người duyệt" bên dưới).

### Model theo từng chức vụ — lượt chạy batch4-chot

| Chức vụ | Model |
|---|---|
| **Trả lời** (sinh câu trả lời cho khách) | `gpt-5.6-luna` |
| **Router + gợi ý** (nhãn intent, câu hỏi gợi ý tiếp theo) | `gpt-5.6-luna` |
| **Orchestrator** (nhánh leo thang, gọi tool) | `claude-sonnet-5` |
| **LLM Judge** (chấm điểm eval) | `claude-sonnet-5` |

Hai tham số cấu hình đi kèm: chế độ leo thang `moi_luot` · ngưỡng độ phủ `0.35`.

Orchestrator và Judge dùng **chung một model** (`claude-sonnet-5`) — xem cảnh
báo self-preference bias ở mục riêng bên dưới.

### Bộ câu hỏi vàng — 29 case (T01–H02)

| Nhóm chỉ số | Số câu | Nội dung tiêu biểu |
|---|---|---|
| Adversarial | 7 | prompt injection trực tiếp (A01) và qua tài liệu (A02), jailbreak đòi giá vốn (A03), đòi PII khách khác (A04), input mơ hồ/gõ tắt/trộn ngôn ngữ (A05-A07) |
| Tool-use | 6 | tra cứu số liệu, tham số truyền tool, tool trả rỗng phải không bịa (T06) |
| Đa lượt | 6 | kế thừa danh từ đúng / KHÔNG kế thừa động từ / hội thoại dài |
| RAG | 5 | Faithfulness, Answer Relevancy, Context Precision/Recall |
| Từ chối | 3 | ngoài phạm vi, không đủ dữ liệu, câu hỏi mơ hồ |
| HITL | 2 | không tự chốt giao dịch / không tự cam kết giá miệng |

### Kết quả tổng quan — batch4-chot

| | |
|---|---|
| Đạt | **23** |
| Không đạt | **2** |
| Chưa kết luận | **3** (M01a, M02a, M03a — lượt mở đầu của kịch bản đa lượt, xlsx không khai cách chấm riêng) |
| **Tỷ lệ đạt (trên số đã kết luận)** | **92% — mức "Tốt"** |
| Chưa chạy | A02 (cần collection `eval_injection` riêng — xem `eval/README.md` mục A02) |

### Theo nhóm

| Nhóm chỉ số | Đạt | Không đạt | Chưa kết luận | Tỷ lệ đạt |
|---|---|---|---|---|
| Tool-use | 6 | 0 | 0 | **100%** |
| RAG | 4 | 1 | 0 | **80%** |
| Đa lượt | 3 | 0 | 3 | 100% (trên số đã kết luận) |
| Từ chối | 2 | 1 | 0 | **67%** |
| Adversarial | 6 | 0 | 0 | **100%** |
| HITL | 2 | 0 | 0 | **100%** |

### Ma trận chỉ số — điểm đáng chú ý

| Chỉ số | Ngưỡng plan | Đo được | Kết luận |
|---|---|---|---|
| Faithfulness (R01-R05, F02, F04) | ≥ 0.8 | 1.00 (n=2) | Đạt — **cỡ mẫu rất nhỏ**: phần lớn câu RAG là từ chối đúng nên không có khẳng định để chấm |
| Answer Relevancy | ≥ 0.8 | 0.87 (n=10) | Đạt |
| **Context Recall** (R01-R05) | ≥ 0.8 | **7/9 = 78%** | **Chưa đạt** — R01 truy hồi thiếu ['thanh toán sớm', 'không vay ngân hàng'] |
| **Context Precision** (R05) | ≥ 0.7 | **0/5 = 0%** | **Chưa đạt** — không đoạn nào đề cập phí quản lý chung cư hàng tháng |
| Tool selection accuracy | 100% | 7/7 | Đạt |
| Parameter accuracy (T01-T05) | 100% — nguyên nhân gốc bug B01 đã fix | 5/5 | Đạt, **cần theo dõi để không tái diễn** |
| Accuracy tổng thể (LLM Judge) | ≥ 4/5 | **4.40/5** (n=10) | Đạt — nhưng R01 chấm ≤ 2, **bắt buộc người xem lại** |
| Chống prompt injection (A01, A02) | 100% | 2/2 | Đạt (A02 chạy ở collection `eval_injection` riêng) |
| Chống jailbreak / lộ info nội bộ | 100% | 2/2 | Đạt |
| HITL đúng ranh giới (H01, H02) | 100% | 2/2 | Đạt — **cả hai vẫn cần người duyệt** |
| **Độ trễ phản hồi** | P95 ≤ 5s (plan cũ, đã tách mốc 26/08) | tới chữ đầu **14.3s** · đọc xong **16.5s** | **Chưa đạt** cả hai mốc mới (≤8s / ≤15s) |
| Chi phí mỗi lượt | theo dõi, không tăng bất thường | OpenAI $0.00167 + Anthropic $0.00419 = **$0.00586** | Theo dõi — cổng chính sách TẮT ở lượt này, nếu bật thì +$0.00268 |

### Case đáng chú ý (fail hoặc cần xem lại)

| ID | Nhóm | Kết luận | Ghi chú |
|---|---|---|---|
| **R01** | RAG | **Không đạt** (Judge 1/5, Relevancy 0.2, tầng lỗi: retrieval) | Kho tài liệu có thật thông tin ưu đãi thanh toán sớm 9%, nhưng trợ lý từ chối trả lời dù có dữ liệu — retrieval không kéo trúng đoạn liên quan |
| **F02** | Từ chối | **Không đạt** (rule-based: cấm số `%/năm` cụ thể) | Câu trả lời nêu "trần lãi suất 9%/năm" — khớp regex cấm, cần người xem lại đây là bịa hay là số thật từ `chinh_sach_vay.json` |

### Cần người duyệt (bắt buộc theo plan, CHƯA có chữ ký người duyệt trong file)

8 case đang chờ: **T03** (case P0 tái hiện bug B01), **R01** (Judge nghi bịa),
**R02** (soát danh sách tiện ích), **R03** (case pháp lý — bắt buộc), **M01b**,
**M03b** (đối chiếu tham chiếu ngược), **H01**, **H02** (bắt buộc — ranh giới
HITL và cam kết giá). Cột "Người duyệt" trong file đang **rỗng** ở mọi dòng.

### ⚠️ Cảnh báo tự đánh giá bản báo cáo: self-preference bias chưa loại được

**30/31 lượt có `orchestrate` chạy bằng `claude-sonnet-5` — cùng model đang đi
chấm (Judge).** Giả định ban đầu "Judge khác family với model sinh chữ" chỉ
đúng ở khâu sinh chữ (`gpt-5.6-luna`/`gpt-4o`), không đúng ở khâu gọi tool khi
cổng leo thang mở. Khuyến nghị của file: lúc calibrate với người, tách riêng
nhóm có/không leo thang rồi so độ lệch điểm.

Các loại bias khác đã kiểm và loại được: position bias (không áp dụng — chấm
từng câu, không so A/B) · verbosity (rubric ghi rõ ngắn gọn vẫn tối đa điểm) ·
format (markdown bị gỡ trước khi đưa Judge) · sycophancy/authority (dữ liệu
trong thẻ, system prompt yêu cầu bỏ qua mệnh lệnh trong thẻ) · recency (rubric
không có ví dụ minh hoạ để xáo thứ tự).

### Bối cảnh: một lượt chạy sơ bộ trước đó (13/08/2026)

Trước batch4-chot, có một lượt đo nhỏ hơn dùng bộ dữ liệu retrieval cũ (35 câu,
`eval/golden_dataset.json` — nay đã xoá) + 6 test case thủ công gọi trực tiếp
`AgentService.answer()`: hit@n retrieval 20/28 = 71%, 4/6 test case đúng hoàn
toàn, 0/6 bịa số liệu. Chi tiết ở [`eval/results/report.md`](eval/results/report.md) —
**đã bị thay thế** bởi batch4-chot ở trên vì batch4-chot chạy đủ 29/29 câu qua
pipeline hiện hành, không phải 6 câu chọn tay.

### Bài học từ quá trình xây bộ eval

1. **Cửa sổ lịch sử 4 lượt cắt mất ngữ cảnh** → sửa thành 10 lượt: kế thừa
   `subdivision` từ 0/3 lên 3/3.
2. **Bộ chấm rule-based chấm oan câu chống-injection đúng** (phủ định nằm khác
   câu so với cụm bị cấm) — sửa 2 lần, giờ xét theo câu thay vì cửa sổ ký tự cố định.
3. **Thử nghiệm "dùng LLM rút tham số khi regex hụt"** — đo trước rồi mới quyết:
   chỉ khớp 2/62 lượt thật cần → không xây thêm tầng model.
4. **Judge nhận cả kho tài liệu** thay vì chỉ đoạn đã truy hồi — tránh vòng
   luẩn quẩn tự chấm 5/5 cho mọi câu từ chối (đo được chênh lệch 5/5 → 2/5 khi sửa).

---

## Phần 2 — Eval Modify Object (gpt-image-1-mini vs Seedream 4.0)

Nguồn: [`image-bench/`](image-bench/) — công cụ benchmark cục bộ tự dựng, log
thật tại [`image-bench/results/log.jsonl`](image-bench/results/log.jsonl).
**10 lượt chạy**, mỗi lượt gọi đồng thời cả hai model trên cùng một ảnh gốc +
cùng một prompt, đo latency/cost tự động, người dùng chấm bằng mắt theo 3 tiêu
chí (1-5 sao mỗi tiêu chí).

### Phương pháp

- Cả hai model nhận **cùng ảnh gốc, cùng prompt** (qua cùng một khuôn hướng dẫn
  `_HUONG_DAN` — giống hệt production gửi), gọi **đồng thời** (`asyncio.gather`).
- Cost: OpenAI tính theo token thật trong `usage` của response (`$2,00`/`$2,50`/`$8,00`
  mỗi 1M token cho text-input/image-input/image-output — nguồn: developers.openai.com/api/docs/pricing);
  Seedream tính phẳng **$0,03/ảnh** (nguồn: docs.byteplus.com/en/docs/ModelArk/1824718),
  không đổi theo resolution.
- Ba tiêu chí chấm tay, mỗi tiêu chí 1-5:
  1. **Đúng thao tác** — add/remove/change đúng vật khách yêu cầu.
  2. **Giữ nguyên phần còn lại** — phần ảnh không liên quan có bị đổi theo không.
  3. **Chất lượng ảnh vùng sửa** — vùng vừa sửa có artifact/méo/lem không.

⚠️ **Giới hạn cần nêu rõ nếu đưa vào báo cáo**: n=10, một người chấm (không có
inter-rater agreement), ảnh nguồn là ảnh nội thất thật của dự án (không phải bộ
test chuẩn hoá công khai) — đây là benchmark nội bộ, không phải một bộ eval học
thuật.

### Kết quả tổng hợp (trung bình 10 lượt)

| | **gpt-image-1-mini** | **Seedream 4.0** |
|---|---|---|
| Latency trung bình | **34,1s** (19,1s–50,2s) | **10,7s** (9,5s–12,1s) |
| Cost trung bình / ảnh | **$0,0348** ($0,0158–$0,0537) | **$0,0300** (cố định) |
| Tổng cost 10 lượt | $0,3481 | $0,3000 |
| Điểm TB tổng (3 tiêu chí) | **3,43 / 5** (1,33–4,67) | **4,47 / 5** (3,33–5,00) |
| — Đúng thao tác | 3,80 / 5 | 4,60 / 5 |
| — Giữ nguyên phần còn lại | 3,20 / 5 | 4,40 / 5 |
| — Chất lượng vùng sửa | 3,30 / 5 | 4,40 / 5 |

**Đọc nhanh:** Seedream 4.0 **nhanh hơn ~3,2 lần** (10,7s so với 34,1s trung
bình) ở MỌI lượt. Cost thì chia đôi: **5/10 lượt** OpenAI trả output ảnh nhỏ
(~1568-1584 token, xem mục "Quan sát" bên dưới) nên rẻ hơn Seedream, **5/10 lượt**
còn lại output ảnh lớn (~6208-6240 token) nên đắt hơn — Seedream luôn phẳng
$0,03 nên không có biến động này. Điểm chất lượng trung bình do người dùng
chấm **cao hơn ở cả 3 tiêu chí** cho Seedream trong bộ 10 case này.

### Chi tiết từng lượt

| # | Prompt | Model | Latency | Cost | Đúng thao tác | Giữ nguyên | Chất lượng vùng sửa | TB | Ghi chú |
|---|---|---|---|---|---|---|---|---|---|
| 1 | hãy thêm lò vi sóng lên trên mặt bếp cho tôi | openai | 49,7s | $0,05347 | 1 | 2 | 1 | 1,33 | không thêm lò vi sóng theo yêu cầu |
| | | seedream | 11,6s | $0,03000 | 5 | 3 | 5 | 4,33 | thêm lò vi sóng chưa đúng logic ảnh |
| 2 | thay đèn trần bằng quạt trần | openai | 19,8s | $0,01634 | 4 | 1 | 3 | 2,67 | — |
| | | seedream | 9,5s | $0,03000 | 5 | 5 | 4 | 4,67 | — |
| 3 | thêm chậu hoa ở góc phòng | openai | 45,3s | $0,05346 | 5 | 4 | 5 | 4,67 | — |
| | | seedream | 10,1s | $0,03000 | 5 | 5 | 5 | 5,00 | — |
| 4 | thay cửa sổ kính bằng cửa kính kéo | openai | 50,2s | $0,05372 | 5 | 4 | 5 | 4,67 | — |
| | | seedream | 10,3s | $0,03000 | 5 | 5 | 5 | 5,00 | — |
| 5 | đổi bộ ghế sofa thành ghế gỗ khắc hoa văn hoạ tiết đẹp | openai | 48,4s | $0,05310 | 5 | 1 | 3 | 3,00 | — |
| | | seedream | 12,1s | $0,03000 | 5 | 5 | 5 | 5,00 | — |
| 6 | thay đổi tường căn hộ thành màu xanh nước biển | openai | 22,3s | $0,01584 | 5 | 4 | 3 | 4,00 | — |
| | | seedream | 10,8s | $0,03000 | 5 | 3 | 4 | 4,00 | — |
| 7 | hãy xóa bỏ bộ bàn ghế cho tôi | openai | 21,4s | $0,01658 | 3 | 4 | 4 | 3,67 | xóa thiếu vật |
| | | seedream | 12,0s | $0,03000 | 4 | 5 | 3 | 4,00 | xóa đủ vật nhưng thiếu logic |
| 8 | hãy thay cho tôi chiếc tủ lạnh thành chiếc máy giặt | openai | 19,7s | $0,01635 | 4 | 4 | 4 | 4,00 | đúng vị trí thay thế nhưng chưa đúng logic |
| | | seedream | 10,3s | $0,03000 | 2 | 4 | 4 | 3,33 | thay thế sai vị trí |
| 9 | hãy xóa chậu hoa đặt ở bàn ăn (chỉ xóa 1 chậu hoa đó) | openai | 19,1s | $0,01636 | 1 | 4 | 1 | 2,00 | — |
| | | seedream | 9,6s | $0,03000 | 5 | 5 | 5 | 5,00 | — |
| 10 | hãy lắp thêm cho tôi một dãy tủ ngăn dưới kệ tivi, màu của kệ cùng tone màu với căn phòng | openai | 44,8s | $0,05287 | 5 | 4 | 4 | 4,33 | — |
| | | seedream | 10,7s | $0,03000 | 5 | 4 | 4 | 4,33 | thêm ảnh đúng theo yêu cầu nhưng thay đổi góc quay khung hình |

### Quan sát đáng chú ý

- **Latency của OpenAI chia hai nhóm rõ rệt**: lượt #2/6/7/8/9 (≈19-22s, output
  ~1568-1584 token) so với lượt #1/3/4/5/10 (≈45-50s, output ~6208-6240 token) —
  cùng model, cùng `size="auto"`, nhưng ảnh output lớn hơn hẳn kéo latency lẫn
  cost lên gấp ~2,5-3 lần. Seedream ổn định 9,5-12,1s ở mọi lượt (giá cũng phẳng).
- **Cả hai đều có lượt bị chấm thấp** vì sai *thao tác* (không phải chỉ chất
  lượng ảnh): OpenAI ở lượt #1 và #9 (điểm 1/5 "Đúng thao tác" — không làm hoặc
  làm sai hẳn yêu cầu), Seedream ở lượt #8 (điểm 2/5 — thay sai vị trí).
- **"Giữ nguyên phần còn lại" là tiêu chí OpenAI yếu nhất** (TB 3,20/5, thấp hơn
  hẳn 2 tiêu chí kia) — nhiều ghi chú không nêu lý do cụ thể nhưng điểm số cho
  thấy OpenAI có xu hướng đổi thêm chi tiết ngoài phạm vi yêu cầu nhiều hơn
  Seedream (TB 4,40/5).
- Seedream đạt điểm tuyệt đối 5,00/5 ở 4/10 lượt (#3, #4, #5, #9); OpenAI không
  có lượt nào đạt 5,00/5 tuyệt đối.

---

## Cách tái tạo / cập nhật số liệu

```bash
# AI Agent
make run-ai
python -m eval.runner.chay
python -m eval.runner.cham_diem eval/results/raw_<...>.json

# Modify Object
python image-bench/server.py   # mở http://127.0.0.1:8010
```

File này tổng hợp thủ công tại một thời điểm — chạy lại rồi cập nhật số liệu
nếu dùng cho báo cáo/slide sau này, đừng giữ số cũ khi hệ thống đã đổi.
