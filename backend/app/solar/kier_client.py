from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

import requests


@dataclass
class KierSolarResult:
    fetched_at: float
    date: str      # YYYYMMDD
    time: str      # HHMM
    lat: float
    lot: float     # 경도 (명세상 lot)
    items: List[Dict[str, Any]]
    raw: Dict[str, Any]


class KierSolarClient:
    """
    한국에너지기술연구원 일사량 예측(위경도) API
    endpoint 예:
      BASE_URL = https://apis.data.go.kr/B551184/SrQtyService/getSrQtyPredcInfo
    params:
      serviceKey, pageNo, numOfRows, type, date, time, lat, lot
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

    def is_configured(self) -> bool:
        return bool(self.base_url) and bool(self.service_key)

    def fetch_predc(
        self,
        *,
        lat: float,
        lot: float,
        date: str,
        time_hhmm: str,
        page_no: int = 1,
        num_rows: int = 10,
        resp_type: str = "json",
    ) -> Optional[KierSolarResult]:
        if not self.is_configured():
            return None

        params = {
            "serviceKey": self.service_key,
            "pageNo": int(page_no),
            "numOfRows": int(num_rows),
            "type": resp_type,
            "date": date,
            "time": time_hhmm,
            "lat": float(lat),
            "lot": float(lot),  # ✅ 명세대로 lot
        }

        try:
            r = requests.get(self.base_url, params=params, timeout=self.timeout_sec)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None

        items = self._extract_items(data)

        return KierSolarResult(
            fetched_at=time.time(),
            date=date,
            time=time_hhmm,
            lat=float(lat),
            lot=float(lot),
            items=items,
            raw=data,
        )

    def _extract_items(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            resp = data.get("response") if isinstance(data, dict) else None
            body = resp.get("body") if isinstance(resp, dict) else None
            items = body.get("items") if isinstance(body, dict) else None
            item = items.get("item") if isinstance(items, dict) else None

            if isinstance(item, list):
                return item
            if isinstance(item, dict):
                return [item]
        except Exception:
            pass

        return []
