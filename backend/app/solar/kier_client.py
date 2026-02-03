from __future__ import annotations

import os, time, requests, json
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple
from urllib.parse import unquote
import xml.etree.ElementTree as ET


@dataclass
class KierSolarResult:
    fetched_at: float
    date: str
    time: str
    lat: float
    lon: float
    items: List[Dict[str, Any]]
    raw: Dict[str, Any]


class KierSolarClient:
    """
    KIER(공공데이터포털) 일사량 예측 API 호출기.

    swagger 기준 파라미터(중요):
      - serviceKey, pageNo, numOfRows, type, date, time, lat, lot
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_key: Optional[str] = None,
        timeout_sec: int = 8,
    ) -> None:
        self.base_url = (base_url or os.getenv("KIER_SOLAR_BASE_URL", "")).strip()

        # ✅ 이미 붙어있는 query (? 뒤) 제거 — endpoint만 남긴다
        if "?" in self.base_url:
            self.base_url = self.base_url.split("?", 1)[0]

        self.service_key = (service_key or os.getenv("KIER_SOLAR_SERVICE_KEY", "")).strip()
        self.timeout_sec = int(timeout_sec)

        # serviceKey 더블 인코딩 방지
        # if "%" in self.service_key:
        #     self.service_key = unquote(self.service_key)

        # base_url 보정: scheme 없으면 https 붙임
        if self.base_url and not self.base_url.startswith(("http://", "https://")):
            self.base_url = "https://" + self.base_url.lstrip("/")

        print("[KIER][CONF] base_url =", self.base_url)
        print("[KIER][CONF] key_len  =", len(self.service_key))

    def is_configured(self) -> bool:
        return bool(self.base_url) and bool(self.service_key)

    # -------------------------
    # Public
    # -------------------------
    def fetch_predc_simple(
        self,
        *,
        lat: float,
        lon: float,
        date: str,
        hhmm: str = "1200",
    ) -> Optional[KierSolarResult]:
        return self.fetch_predc(lat=lat, lon=lon, date=date, time_hhmm=hhmm)

    def fetch_predc(
            self, *,
            lat: float,
            date: str,
            time_hhmm: str,
            lon: Optional[float] = None,
            lot: Optional[float] = None,
            page_no: int = 1,
            num_rows: int = 200,
    ) -> Optional[KierSolarResult]:

        if not self.is_configured():
            print("[KIER][ERR] not configured")
            return None

        lon_v = lon if lon is not None else lot
        if lon_v is None:
            print("[KIER][ERR] missing longitude")
            return None

        # 1. 날짜 및 시간 포맷 정밀 보정
        d_try = str(date).strip().replace("-", "")  # YYYYMMDD

        # [중요] 에러 10번 해결책: "1200" 대신 "12"만 요구하는 경우가 많음
        t_raw = (time_hhmm or "").strip().replace(":", "")
        t_val = t_raw[:2] if len(t_raw) >= 2 else "12"

        # 2. 서비스키 디코딩
        final_key = unquote(self.service_key)

        # 3. 파라미터 조합 (에러 10번 방지를 위해 소수점 제한 및 명칭 최적화)
        params = {
            "serviceKey": final_key,
            "pageNo": str(page_no),
            "numOfRows": str(num_rows),
            "dataType": "JSON",
            "date": d_try,
            "time": t_val,  # HHMM이 아니라 HH일 가능성 적용
            "lat": str(round(float(lat), 4)),  # 소수점 너무 길면 에러날 수 있음
            "lot": str(round(float(lon_v), 4)),
        }

        url = self.base_url.split("?", 1)[0]

        # 4. 호출 및 URL 출력 (여기서 확인 가능합니다)
        r = requests.get(url, params=params, timeout=self.timeout_sec)

        print("-" * 50)
        print(f"[KIER][HTTP] status = {r.status_code}")
        print(f"[KIER][HTTP] url    = {r.url}")  # 이 URL을 복사해서 브라우저에 붙여넣으세요!
        print("-" * 50)

        data = self._safe_parse_body(r)
        code, msg = self._extract_header_code_msg(data)
        print(f"[KIER][PARSE] resultCode={code} msg={msg}")

        if str(code) != "00":
            print("[KIER][PARSE][FAIL_BODY_HEAD]", (r.text or "")[:300])
            return None

        items = self._extract_items(data)
        if not items:
            return None

        return KierSolarResult(
            fetched_at=time.time(),
            date=d_try,
            time=t_val,
            lat=float(lat),
            lon=float(lon_v),
            items=items,
            raw=data if isinstance(data, dict) else {"raw": data},
        )

    # -------------------------
    # Internals
    # -------------------------
    def _safe_parse_body(self, r: requests.Response) -> Any:
        txt = (r.text or "").strip()

        # 1) JSON
        try:
            return r.json()
        except Exception:
            pass

        # 2) XML
        if txt.startswith("<"):
            try:
                return self._xml_to_dict(txt)
            except Exception as e:
                print("[KIER][ERR] xml parse failed:", e)
                return {"raw_text_head": txt[:300]}

        # 3) HTML/기타
        return {"raw_text_head": txt[:300]}

    def _xml_to_dict(self, xml_text: str) -> Dict[str, Any]:
        root = ET.fromstring(xml_text)

        def strip_tag(tag: str) -> str:
            return tag.split("}", 1)[-1] if "}" in tag else tag

        def node_to_obj(node: ET.Element) -> Any:
            children = list(node)
            if not children:
                return (node.text or "").strip()
            d: Dict[str, Any] = {}
            for ch in children:
                k = strip_tag(ch.tag)
                v = node_to_obj(ch)
                if k in d:
                    if not isinstance(d[k], list):
                        d[k] = [d[k]]
                    d[k].append(v)
                else:
                    d[k] = v
            return d

        return {strip_tag(root.tag): node_to_obj(root)}

    def _extract_header_code_msg(self, data: Any) -> Tuple[str, str]:
        if isinstance(data, dict):
            # JSON: response.header.resultCode/resultMsg
            resp = data.get("response")
            if isinstance(resp, dict):
                header = resp.get("header")
                if isinstance(header, dict):
                    return str(header.get("resultCode") or ""), str(header.get("resultMsg") or "")

            # XML dict 등 fallback
            code = self._deep_get(data, ["response", "header", "resultCode"]) or self._deep_find_key(data, "resultCode")
            msg = self._deep_get(data, ["response", "header", "resultMsg"]) or self._deep_find_key(data, "resultMsg")
            return str(code or ""), str(msg or "")

        return "", ""

    def _extract_items(self, data: Any) -> List[Dict[str, Any]]:
        if not isinstance(data, dict):
            return []

        resp = data.get("response")
        if isinstance(resp, dict):
            body = resp.get("body")
            if isinstance(body, dict):
                items = body.get("items")
                if isinstance(items, dict):
                    item = items.get("item")
                    if isinstance(item, list):
                        return [x for x in item if isinstance(x, dict)]
                    if isinstance(item, dict):
                        return [item]

        found = self._deep_find_key(data, "item")
        if isinstance(found, list):
            return [x for x in found if isinstance(x, dict)]
        if isinstance(found, dict):
            return [found]
        return []

    def _deep_get(self, d: Dict[str, Any], path: List[str]) -> Any:
        cur: Any = d
        for p in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(p)
        return cur

    def _deep_find_key(self, d: Any, target_key: str) -> Any:
        if isinstance(d, dict):
            if target_key in d:
                return d[target_key]
            for v in d.values():
                got = self._deep_find_key(v, target_key)
                if got is not None:
                    return got
        elif isinstance(d, list):
            for x in d:
                got = self._deep_find_key(x, target_key)
                if got is not None:
                    return got
        return None
