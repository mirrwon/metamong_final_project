from __future__ import annotations

import os
import time
import requests
from dataclasses import dataclass
from typing import Any, Dict, Optional, List
from urllib.parse import unquote

@dataclass
class KierSolarResult:
    fetched_at: float
    date: str      # YYYYMMDD
    time: str      # HH or HHMM (요청에 사용한 값 그대로)
    lat: float
    lot: float
    items: List[Dict[str, Any]]
    raw: Dict[str, Any]


class KierSolarClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        service_key: Optional[str] = None,
        timeout_sec: int = 8,
    ) -> None:
        self.base_url = (base_url or os.getenv("KIER_SOLAR_BASE_URL", "")).strip()
        self.service_key = (service_key or os.getenv("KIER_SOLAR_SERVICE_KEY", "")).strip()
        self.timeout_sec = int(timeout_sec)

        # 🔥 핵심 1) serviceKey 더블-인코딩 방지
        # env에 Encoding 키(%)가 들어있으면 requests가 %를 다시 인코딩해서 invalid가 자주 남.
        # 일단 unquote 한번 해서 "디코딩키" 형태로 보냄.
        if "%" in self.service_key:
            self.service_key = unquote(self.service_key)

        print("[KIER][KEY] raw_len =", len(os.getenv("KIER_SOLAR_SERVICE_KEY", "") or ""))
        print("[KIER][KEY] used_len =", len(self.service_key))

    def is_configured(self) -> bool:
        return bool(self.base_url) and bool(self.service_key)

    def fetch_predc_simple(self, *, lat: float, lot: float, date: str) -> None:
        params = {
            "serviceKey": self.service_key,
            "dataType": "JSON",
            "pageNo": 1,
            "numOfRows": 10,
            "date": date,
            "time": "1200",
            "lat": lat,
            "lot": lot,
        }

        service_key = self.service_key
        url = f"{self.base_url}?serviceKey={service_key}"

        r = requests.get(url, params=params, timeout=self.timeout_sec)
        print("[KIER][SIMPLE] status =", r.status_code)

        try:
            data = r.json()
            header = data.get("response", {}).get("header", {})
            print("[KIER][SIMPLE] resultCode =", header.get("resultCode"),
                  "msg =", header.get("resultMsg"))
            print("[KIER][SIMPLE] body keys =", data.get("response", {}).get("body", {}).keys())
        except Exception as e:
            print("[KIER][SIMPLE] json parse error:", e)

    def fetch_predc(
        self,
        *,
        lat: float,
        lot: float,
        date: str,
        time_hhmm: str,
        page_no: int = 1,
        num_rows: int = 200,
    ) -> Optional[KierSolarResult]:
        if not self.is_configured():
            print("[KIER][ERR] not configured: KIER_SOLAR_BASE_URL / KIER_SOLAR_SERVICE_KEY")
            return None

        # 🔥 핵심 2) time 형식 후보들 (HHMM / HH)
        # time은 무조건 HHMM(4자리)만 보냄 (KIER가 HH만 받는 경우 거의 없음)

        # ✅ 이 코드로 교체
        t = (time_hhmm or "").strip().replace(":", "")
        if len(t) >= 2 and t[:2].isdigit():
            hh = int(t[:2])
        else:
            hh = 12

        # KIER는 HH00 형식만 정상
        tval = f"{hh:02d}00"

        # ✅ time 후보 (서비스가 time을 어떤 형식으로 받는지 스펙이 애매해서 실측 기반으로 맞춘다)
        # - "1100" (HHMM)
        # - "11"   (HH)
        # - "110000" (HHMMSS) 케이스 대비
        # - None (time 파라미터를 아예 빼고 호출)
        time_candidates: List[Optional[str]] = [tval, f"{hh:02d}", f"{hh:02d}0000", None]

        date_candidates = [date]
        # YYYYMMDD -> YYYY-MM-DD 후보 추가
        if isinstance(date, str) and len(date) == 8 and date.isdigit():
            date_candidates.append(f"{date[:4]}-{date[4:6]}-{date[6:8]}")

        # 주변 1~6시간 폴백 (실시간 서비스는 특정 시간대만 유효할 수 있음)
        for back in range(1, 7):
            h2 = (hh - back) % 24
            time_candidates.append(f"{h2:02d}00")
            time_candidates.append(f"{h2:02d}")

        # 🔥 핵심 3) 응답 타입 파라미터 후보들: dataType=JSON / _type=json / type=json

        # ✅ 응답 타입은 type=json )
        type_candidates = [("type", "json")]

        for type_key, type_val in type_candidates:
            for d_try in date_candidates:
                for t_try in time_candidates:
                    params = {
                        "serviceKey": self.service_key,
                        "pageNo": int(page_no),
                        "numOfRows": int(num_rows),
                        type_key: type_val,  # type=json
                        "date": date,
                        "lat": str(lat),
                        "lot": str(lot),
                    }

                    # ✅ time이 None이면 아예 파라미터에서 제거
                    if t_try is not None:
                        params["time"] = str(t_try)

                    try:
                        # r = requests.get(self.base_url, params=params, timeout=self.timeout_sec)
                        # 🔥 serviceKey를 URL에 직접 붙여서 호출 (인코딩 꼬임 테스트)
                        params2 = dict(params)  # 원본 보호
                        service_key = params2.pop("serviceKey")  # params에서 제거

                        url = f"{self.base_url}?serviceKey={service_key}"
                        r = requests.get(url, params=params2, timeout=self.timeout_sec)

                        print("[KIER][HTTP] status =", r.status_code)
                        print("[KIER][HTTP] url =", r.url)

                        r.raise_for_status()
                        data = r.json()
                    except Exception as e:
                        print("[KIER][ERR] request failed:", e)
                        continue

                    header = None
                    if isinstance(data, dict):
                        resp = data.get("response")
                        if isinstance(resp, dict):
                            header = resp.get("header")

                    code = ""
                    msg = ""
                    if isinstance(header, dict):
                        code = str(header.get("resultCode") or "")
                        msg = str(header.get("resultMsg") or "")

                    print("[KIER][PARSE] resultCode =", code, "resultMsg =", msg, f"(time={t_try}, type=json)")

                    if code and code != "00":
                        continue

                    items = self._extract_items(data)
                    print("[KIER][PARSE] items_len =", len(items))

                    if len(items) == 0:
                        continue

                    return KierSolarResult(
                        fetched_at=time.time(),
                        date=date,
                        time=str(t_try) if t_try is not None else "",
                        lat=float(lat),
                        lot=float(lot),
                        items=items,
                        raw=data,
                    )

        return None

    def _extract_items(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(data, dict):
            return []

        try:
            resp = data.get("response")
            body = resp.get("body") if isinstance(resp, dict) else None
            items = body.get("items") if isinstance(body, dict) else None
            item = items.get("item") if isinstance(items, dict) else None

            if isinstance(item, list):
                return [x for x in item if isinstance(x, dict)]
            if isinstance(item, dict):
                return [item]
        except Exception:
            pass

        return []