from __future__ import annotations

import os
import time
import requests
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
    KIER(공공데이터포털) 일사량 API 호출기.

    핵심:
    - resultCode=11(필수 파라미터 없음)이 '값' 문제가 아니라 '키 이름' 불일치인 경우가 많음.
    - 그래서 baseDate/baseTime/latitude/longitude 뿐 아니라 base_date/base_time, lat/lon 별칭을
      "제한된 조합"으로만 시도한다. (무한 루프/로그 폭발 방지)
    - _type=json 같은건 HTML/XML 내려주는 케이스 많아서 제거.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_key: Optional[str] = None,
        timeout_sec: int = 8,
    ) -> None:
        self.base_url = (base_url or os.getenv("KIER_SOLAR_BASE_URL", "")).strip()
        self.service_key = (service_key or os.getenv("KIER_SOLAR_SERVICE_KEY", "")).strip()
        self.timeout_sec = int(timeout_sec)


        # serviceKey 더블 인코딩 방지
        if "%" in self.service_key:
            self.service_key = unquote(self.service_key)

        print("[KIER][CONF] base_url =", self.base_url)
        print("[KIER][CONF] key_len  =", len(self.service_key))

    def is_configured(self) -> bool:
        return bool(self.base_url) and bool(self.service_key)

    # -------------------------
    # Public
    # -------------------------
    def fetch_predc_simple(self, *, lat: float, lon: float, date: str, hhmm: str = "1200") -> Optional[KierSolarResult]:
        return self.fetch_predc(lat=lat, lon=lon, date=date, time_hhmm=hhmm)

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
            print("[KIER][ERR] not configured")
            return None

        endpoint = "/getSrQtyPredcInfo"
        url = self.base_url.rstrip("/") + endpoint

        print("LOCAL_DATE=", time.strftime("%Y%m%d"))

        # ---- normalize date ----
        d = (date or "").strip().replace("-", "")
        if not (len(d) == 8 and d.isdigit()):
            d = time.strftime("%Y%m%d")
        yr, mm, day = d[:4], d[4:6], d[6:8]

        # ---- normalize time ----
        t = (time_hhmm or "").strip().replace(":", "")
        hh_int = int(t[:2]) if len(t) >= 2 and t[:2].isdigit() else 12
        hh = f"{hh_int:02d}00"  # 1200

        url = f"{self.base_url}?serviceKey={self.service_key}"

        # =========================
        # 1) ✅ yr/mm/day/hh/lat/lot ONLY (너가 브라우저에서 성공한 포맷)
        # =========================
        params = {
            "dataType": "JSON",
            "pageNo": int(page_no),
            "numOfRows": int(num_rows),
            "yr": yr,
            "mm": mm,
            "day": day,
            "hh": hh,
            "lat": str(lat),
            "lot": str(lot),
        }

        r = requests.get(url, params=params, timeout=self.timeout_sec)
        print("[KIER][HTTP] status =", r.status_code)
        print("[KIER][HTTP] url    =", r.url)

        data = self._safe_parse_body(r)
        code, msg = self._extract_header_code_msg(data)
        print(f"[KIER][PARSE] resultCode={code} msg={msg}")

        if str(code) != "00":
            print("[KIER][ERR_BODY_HEAD]", (r.text or "")[:300])
            return None

        items = self._extract_items(data)
        print("[KIER][PARSE] items_len =", len(items))
        if not items:
            return None

        return KierSolarResult(
            fetched_at=time.time(),
            date=d,
            time=hh,
            lat=float(lat),
            lot=float(lot),
            items=items,
            raw=data if isinstance(data, dict) else {"raw": data},
        )

    # -------------------------
    # Internals
    # -------------------------
    def _safe_parse_body(self, r: requests.Response) -> Any:
        """
        JSON 실패하면 XML 파싱 시도.
        """
        txt = (r.text or "").strip()

        # 1) JSON 시도
        try:
            return r.json()
        except Exception:
            pass

        # 2) XML 시도
        if txt.startswith("<"):
            try:
                return self._xml_to_dict(txt)
            except Exception as e:
                print("[KIER][ERR] xml parse failed:", e)
                return {"raw_text_head": txt[:300]}

        # 3) 기타(HTML 등)
        return {"raw_text_head": txt[:300]}

    def _xml_to_dict(self, xml_text: str) -> Dict[str, Any]:
        """
        data.go.kr 스타일 XML을 dict 비슷하게.
        """
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
                # 같은 태그가 여러 번 나오면 list로
                if k in d:
                    if not isinstance(d[k], list):
                        d[k] = [d[k]]
                    d[k].append(v)
                else:
                    d[k] = v
            return d

        return {strip_tag(root.tag): node_to_obj(root)}

    def _extract_header_code_msg(self, data: Any) -> Tuple[str, str]:
        """
        JSON/XML 어디로 와도 resultCode/resultMsg를 최대한 찾아본다.
        """
        if isinstance(data, dict):
            # JSON 케이스: response.header
            resp = data.get("response") if "response" in data else None
            if isinstance(resp, dict):
                header = resp.get("header")
                if isinstance(header, dict):
                    return str(header.get("resultCode") or ""), str(header.get("resultMsg") or "")

            # XML dict 케이스: response/header/resultCode 이런 구조일 수도
            # root가 response일 수도 있으니 전부 탐색
            code = self._deep_get(data, ["response", "header", "resultCode"]) or self._deep_find_key(data, "resultCode")
            msg = self._deep_get(data, ["response", "header", "resultMsg"]) or self._deep_find_key(data, "resultMsg")
            return str(code or ""), str(msg or "")

        return "", ""

    def _extract_items(self, data: Any) -> List[Dict[str, Any]]:
        """
        JSON: response.body.items.item
        XML dict: 비슷한 경로로 최대한 접근
        """
        if not isinstance(data, dict):
            return []

        # JSON 표준 경로
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

        # XML dict fallback: key 이름이 조금 다를 수 있으니 느슨하게 찾기
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
