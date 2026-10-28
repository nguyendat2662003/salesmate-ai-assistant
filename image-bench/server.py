"""Benchmark cục bộ — so sánh gpt-image-1-mini và Seedream 4.0 trên CÙNG một ảnh.

Công cụ RIÊNG cho việc đo đạc, KHÔNG phải một phần sản phẩm: không import
`interface/backend` lẫn `src/`, không đụng kiến trúc Protocol/contract của dự
án — thư mục này nằm ngang hàng với src/ và interface/, không lồng trong
scripts/. Gọi thẳng hai API bằng cùng hình dạng request đã test thật trong
`interface/backend/app/services/image_edit.py`, để số đo phản ánh đúng cái sản
phẩm đang chạy chứ không phải một cách gọi khác.

Đo latency (wall-clock quanh đúng lệnh gọi HTTP của từng model) và cost mỗi
ảnh (công thức xem phần GIA_* bên dưới, có ghi nguồn). Chất lượng ảnh — model
có làm đúng yêu cầu không, có giữ nguyên phần còn lại của ảnh không — do NGƯỜI
DÙNG chấm bằng mắt trên UI, công cụ này không tự đánh giá.

Mỗi lượt chạy được ghi ngay vào `results/log.jsonl` (append), ảnh gốc + ảnh cả
hai model lưu vào `results/images/` — mất kết nối giữa chừng cũng không mất dữ
liệu đã có, và điền điểm đánh giá là một request riêng (theo run_id) nên xem
ảnh xong vài ngày sau mới chấm cũng được.

Chạy:
    pip install fastapi uvicorn httpx python-multipart python-dotenv
    python server.py
Mở http://127.0.0.1:8010

Cần trong `.env` ở gốc repo: OPENAI_API_KEY (đã có sẵn cho lõi AI, dùng lại) và
ARK_API_KEY (BytePlus ModelArk — https://console.byteplus.com/ark, hiện CHƯA
có trong .env của máy này tính đến lúc viết file này).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

_GOC = Path(__file__).resolve().parent
_REPO_ROOT = _GOC.parent
load_dotenv(_REPO_ROOT / ".env")

_KET_QUA_DIR = _GOC / "results"
_ANH_DIR = _KET_QUA_DIR / "images"
_LOG_FILE = _KET_QUA_DIR / "log.jsonl"
_ANH_DIR.mkdir(parents=True, exist_ok=True)

# ---- Cấu hình — cùng TÊN biến môi trường với interface/backend/app/core/config.py,
# để đổi model/size không phải sửa code ở đây lẫn nhớ hai bộ tên khác nhau. ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
OPENAI_IMAGE_SIZE = os.getenv("OPENAI_IMAGE_SIZE", "auto")

ARK_API_KEY = os.getenv("ARK_API_KEY", "")
SEEDREAM_MODEL = os.getenv("SEEDREAM_MODEL", "seedream-4-0-250828")
SEEDREAM_SIZE = os.getenv("SEEDREAM_SIZE", "2K")
SEEDREAM_WATERMARK = os.getenv("SEEDREAM_WATERMARK", "false").lower() == "true"

_API_OPENAI = "https://api.openai.com/v1/images/edits"
_API_SEEDREAM = "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations"

# Cùng hướng dẫn model đúng như production gửi (`_HUONG_DAN` trong image_edit.py) —
# đo benchmark bằng một prompt khác đi thì không còn so sánh cái sản phẩm THẬT
# đang dùng nữa.
_HUONG_DAN = (
    "Bạn đang chỉnh sửa ảnh nội thất của một căn hộ có thật.\n"
    "Yêu cầu của khách: {yeu_cau}\n\n"
    "Chỉ thay đổi đúng thứ khách nêu. Giữ nguyên bố cục phòng, góc chụp, ánh sáng, "
    "kích thước ảnh và mọi đồ vật khác. Không thêm chữ, watermark hay logo vào ảnh."
)

# ---- Giá — xác minh qua tra cứu tài liệu chính thức ngày 29/08/2026, KHÔNG
# phải số đoán:
# OpenAI gpt-image-1-mini, tier standard: https://developers.openai.com/api/docs/pricing
GIA_OPENAI_TEXT_IN = 2.00 / 1_000_000  # $/token
GIA_OPENAI_IMG_IN = 2.50 / 1_000_000
GIA_OPENAI_IMG_OUT = 8.00 / 1_000_000
# BytePlus ModelArk Seedream 4.0 — phẳng, KHÔNG đổi theo resolution:
# https://docs.byteplus.com/en/docs/ModelArk/1824718 ("Unit price is 0.03USD / image")
GIA_SEEDREAM_MOI_ANH = 0.03

_DUOI_THEO_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp"}

# Ba tiêu chí chấm chất lượng ảnh — MỘT chỗ duy nhất khai, cả server lẫn UI đều
# đọc từ đây (qua /api/tieu-chi) để không có hai nơi cùng giữ tên tiêu chí rồi
# trôi lệch khi thêm/sửa một tiêu chí.
TIEU_CHI: list[dict[str, str]] = [
    {"khoa": "dung_thao_tac", "nhan": "Đúng thao tác (add/remove/change đúng vật)"},
    {"khoa": "giu_nguyen", "nhan": "Giữ nguyên phần còn lại"},
    {"khoa": "chat_luong_vung_sua", "nhan": "Chất lượng ảnh vùng sửa (không artifact)"},
]
_KHOA_TIEU_CHI = {tc["khoa"] for tc in TIEU_CHI}


class KetQuaModel(BaseModel):
    ten: str
    thanh_cong: bool
    latency_ms: float | None = None
    cost_usd: float | None = None
    cost_uoc_tinh: bool = False
    anh_b64: str | None = None
    mime: str | None = None
    loi: str | None = None
    raw_usage: dict[str, Any] | None = None


async def _goi_openai(goc: bytes, mime: str, yeu_cau: str) -> KetQuaModel:
    ten = f"openai:{OPENAI_IMAGE_MODEL}"
    if not OPENAI_API_KEY:
        return KetQuaModel(ten=ten, thanh_cong=False, loi="Thiếu OPENAI_API_KEY trong .env ở gốc repo.")

    bat_dau = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                _API_OPENAI,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                data={
                    "model": OPENAI_IMAGE_MODEL,
                    "prompt": _HUONG_DAN.format(yeu_cau=yeu_cau),
                    "n": "1",
                    "size": OPENAI_IMAGE_SIZE,
                },
                files={"image": ("anh-goc", goc, mime)},
            )
    except httpx.HTTPError as exc:
        return KetQuaModel(ten=ten, thanh_cong=False, latency_ms=(time.perf_counter() - bat_dau) * 1000, loi=str(exc))
    latency_ms = (time.perf_counter() - bat_dau) * 1000

    if resp.status_code >= 400:
        return KetQuaModel(
            ten=ten, thanh_cong=False, latency_ms=latency_ms, loi=f"HTTP {resp.status_code}: {resp.text[:400]}"
        )

    data = resp.json()
    muc = (data.get("data") or [{}])[0]
    b64 = muc.get("b64_json")
    if not b64:
        return KetQuaModel(ten=ten, thanh_cong=False, latency_ms=latency_ms, loi="Phản hồi không có ảnh.")

    usage = data.get("usage") or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    chi_tiet = usage.get("input_tokens_details") or {}
    text_tok, img_tok = chi_tiet.get("text_tokens"), chi_tiet.get("image_tokens")
    # Không có breakdown text/ảnh thì coi HẾT input là ảnh (giá cao hơn text) —
    # ước tính theo hướng an toàn hơn là im lặng báo thiếu, đúng tinh thần
    # `da_xac_minh` của gia_model.py: vẫn tính được, chỉ đánh dấu chưa chắc.
    uoc_tinh = text_tok is None or img_tok is None
    if uoc_tinh:
        text_tok, img_tok = 0, input_tokens
    cost = text_tok * GIA_OPENAI_TEXT_IN + img_tok * GIA_OPENAI_IMG_IN + output_tokens * GIA_OPENAI_IMG_OUT

    return KetQuaModel(
        ten=ten,
        thanh_cong=True,
        latency_ms=latency_ms,
        cost_usd=round(cost, 6) if usage else None,
        cost_uoc_tinh=uoc_tinh,
        anh_b64=b64,
        mime="image/png",
        raw_usage=usage or None,
    )


async def _goi_seedream(goc: bytes, mime: str, yeu_cau: str) -> KetQuaModel:
    ten = f"seedream:{SEEDREAM_MODEL}"
    if not ARK_API_KEY:
        return KetQuaModel(ten=ten, thanh_cong=False, loi="Thiếu ARK_API_KEY trong .env ở gốc repo.")

    bat_dau = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                _API_SEEDREAM,
                headers={"Authorization": f"Bearer {ARK_API_KEY}"},
                json={
                    "model": SEEDREAM_MODEL,
                    "prompt": _HUONG_DAN.format(yeu_cau=yeu_cau),
                    "image": f"data:{mime};base64,{base64.b64encode(goc).decode()}",
                    "sequential_image_generation": "disabled",
                    "response_format": "b64_json",
                    "size": SEEDREAM_SIZE,
                    "stream": False,
                    "watermark": SEEDREAM_WATERMARK,
                },
            )
    except httpx.HTTPError as exc:
        return KetQuaModel(ten=ten, thanh_cong=False, latency_ms=(time.perf_counter() - bat_dau) * 1000, loi=str(exc))
    latency_ms = (time.perf_counter() - bat_dau) * 1000

    if resp.status_code >= 400:
        return KetQuaModel(
            ten=ten, thanh_cong=False, latency_ms=latency_ms, loi=f"HTTP {resp.status_code}: {resp.text[:400]}"
        )

    data = resp.json()
    muc = (data.get("data") or [{}])[0]
    b64 = muc.get("b64_json")
    if not b64:
        return KetQuaModel(ten=ten, thanh_cong=False, latency_ms=latency_ms, loi="Phản hồi không có ảnh.")

    return KetQuaModel(
        ten=ten,
        thanh_cong=True,
        latency_ms=latency_ms,
        cost_usd=GIA_SEEDREAM_MOI_ANH,
        cost_uoc_tinh=False,
        anh_b64=b64,
        mime="image/jpeg",
    )


app = FastAPI(title="Image Edit Benchmark (local)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _doc_log() -> list[dict[str, Any]]:
    if not _LOG_FILE.exists():
        return []
    out = []
    with _LOG_FILE.open(encoding="utf-8") as f:
        for dong in f:
            dong = dong.strip()
            if dong:
                out.append(json.loads(dong))
    return out


def _ghi_them_log(record: dict[str, Any]) -> None:
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _ghi_de_log(records: list[dict[str, Any]]) -> None:
    with _LOG_FILE.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@app.post("/api/compare")
async def compare(anh: UploadFile = File(...), prompt: str = Form(...), nhan: str = Form("")) -> JSONResponse:
    goc = await anh.read()
    mime = anh.content_type or "image/jpeg"
    run_id = uuid.uuid4().hex[:12]

    # Gọi ĐỒNG THỜI — đúng ý "so sánh song song" và fair hơn cho latency: cả
    # hai cùng chờ mạng trong một khoảng thời gian trùng nhau thay vì lượt sau
    # ăn ké cache DNS/TLS của lượt trước.
    ket_qua = await asyncio.gather(_goi_openai(goc, mime, prompt), _goi_seedream(goc, mime, prompt))

    ten_goc = f"{run_id}_goc.{_DUOI_THEO_MIME.get(mime, 'jpg')}"
    (_ANH_DIR / ten_goc).write_bytes(goc)

    cho_response: list[dict[str, Any]] = []
    cho_log: list[dict[str, Any]] = []
    for kq in ket_qua:
        d = kq.model_dump()
        if kq.anh_b64:
            ten_an_toan = kq.ten.replace(":", "_").replace(".", "_").replace("-", "_")
            ten_file = f"{run_id}_{ten_an_toan}.{_DUOI_THEO_MIME.get(kq.mime, 'png')}"
            (_ANH_DIR / ten_file).write_bytes(base64.b64decode(kq.anh_b64))
            d["file"] = ten_file
        cho_response.append(d)
        cho_log.append({k: v for k, v in d.items() if k != "anh_b64"})

    record_log = {
        "run_id": run_id,
        "thoi_diem": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "nhan": nhan,
        "prompt": prompt,
        "anh_goc_file": ten_goc,
        "ket_qua": cho_log,
        "danh_gia": {},  # điền qua /api/rate sau khi người dùng xem ảnh
    }
    _ghi_them_log(record_log)

    return JSONResponse({**record_log, "ket_qua": cho_response})


class DanhGiaBody(BaseModel):
    run_id: str
    ten_model: str
    diem: dict[str, int]  # khoá tiêu chí (TIEU_CHI) -> điểm 1-5
    ghi_chu: str = ""


@app.get("/api/tieu-chi")
async def tieu_chi() -> list[dict[str, str]]:
    return TIEU_CHI


@app.post("/api/rate")
async def rate(body: DanhGiaBody) -> dict[str, Any]:
    thieu = _KHOA_TIEU_CHI - set(body.diem)
    if thieu:
        return {"ok": False, "loi": f"Thiếu điểm cho tiêu chí: {', '.join(sorted(thieu))}"}
    sai_khoang = {k: v for k, v in body.diem.items() if not (1 <= v <= 5)}
    if sai_khoang:
        return {"ok": False, "loi": f"Điểm phải trong khoảng 1-5: {sai_khoang}"}

    records = _doc_log()
    for r in records:
        if r["run_id"] == body.run_id:
            trung_binh = round(sum(body.diem.values()) / len(body.diem), 2)
            r.setdefault("danh_gia", {})[body.ten_model] = {
                "diem": body.diem,
                "trung_binh": trung_binh,
                "ghi_chu": body.ghi_chu,
            }
            _ghi_de_log(records)
            return {"ok": True}
    return {"ok": False, "loi": "Không tìm thấy run_id — có thể server đã khởi động lại và log bị mất."}


@app.get("/api/log")
async def log() -> list[dict[str, Any]]:
    return list(reversed(_doc_log()))


@app.get("/anh/{ten_file}", response_model=None)
async def anh(ten_file: str) -> FileResponse | JSONResponse:
    duong_dan = (_ANH_DIR / ten_file).resolve()
    if _ANH_DIR.resolve() not in duong_dan.parents or not duong_dan.exists():
        return JSONResponse({"loi": "Không tìm thấy ảnh."}, status_code=404)
    return FileResponse(duong_dan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_GOC / "index.html")


if __name__ == "__main__":
    import uvicorn

    print(f"OPENAI_API_KEY: {'có' if OPENAI_API_KEY else 'THIẾU'} · ARK_API_KEY: {'có' if ARK_API_KEY else 'THIẾU'}")
    uvicorn.run(app, host="127.0.0.1", port=8010)
