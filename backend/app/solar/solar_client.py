from __future__ import annotations

import os
import time
import json
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests


@dataclass
class SolarProfile:
    """
    제품형 공용 스키마 (일단 최소):
      - ghi_times: morning/noon/evening의 "상대(0~1) 또는 원단위" 값
      - raw: 원본 응답 저장(디버깅/근거)
    """
    provider: str
    fetched_at: float
    lat: float
    lon: float
    ghi_times: Dict[str, float]   # {"morning":..., "noon":..., "evening":...}
    raw: Dict[str, Any]


class SolarClient:
    """
    KIER(또는 다른 solar API) 호출용 클라이언트.

    핵심 설계:
    - base_url, service_key, 파라미터 키 이름들을 .env로 주입 가능
    - 응답(JSON/XML/text) 무엇이 와도 최대한 파싱 시도
    - 실패 시 None 반환(전체 파이프라인이 죽지 않게)
    - 간단 캐시(동일 좌표/시간대 반복 호출 방지)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_key: Optional[str] = None,
        timeout_sec: int = 8,
        cache_ttl_sec: int = 60 * 30,  # 30분 캐시
    ) -> None:
        self.base_url = (base_url or os.getenv("KIER_SOLAR_BASE_URL", "")).strip()
        self.service_key = (service_key or os.getenv("KIER_SOLAR_SERVICE_KEY", "")).strip()
        self.timeout_sec = int(timeout_sec)
        self.cache_ttl_sec = int(cache_ttl_sec)

        # 파라미터 키 이름들(명세마다 다를 수 있어서 env로 분리)
        self.key_service = os.getenv("KIER_PARAM_SERVICE_KEY", "serviceKey").strip()
        self.key_lat = os.getenv("KIER_PARAM_LAT", "lat").strip()
        self.key_lon = os.getenv("KIER_PARAM_LON", "lon").strip()
        self.key_when = os.getenv("KIER_PARAM_WHEN", "when").strip()  # YYYYMMDDHH 등

        # 응답에서 GHI 후보 키(명세 확인 전: 넓게 잡음)
        # 실제 명세 확인하면 여기에 확정 키를 하나로 고정해도 됨
        self.ghi_keys = [
            k.strip().lower()
            for k in os.getenv(
                "KIER_GHI_KEYS",
                "ghi,irradiance,insolation,solar,global,global_horizontal,ghi_wm2,ghi_w_m2",
            ).split(",")
            if k.strip()
        ]

        self._cache: Dict[str, Tuple[float, SolarProfile]] = {}

    def is_configured(self) -> bool:
        return bool(self.base_url) and bool(self.service_key)

    def fetch_profile(
        self,
        lat: float,
        lon: float,
        when_yyyymmddhh: Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[SolarProfile]:
        """
        - when_yyyymmddhh: API가 요구하면 넣고, 아니면 None
        - extra_params: 명세에 base_time/base_date 같은게 있으면 여기에 주입
        """
        if not self.is_configured():
            return None

        lat_f = float(lat)
        lon_f = float(lon)

        cache_key = self._make_cache_key(lat_f, lon_f, when_yyyymmddhh, extra_params)
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {
            self.key_service: self.service_key,
            self.key_lat: lat_f,
            self.key_lon: lon_f,
        }
        if when_yyyymmddhh:
            params[self.key_when] = when_yyyymmddhh
        if extra_params:
            params.update(extra_params)

        try:
            r = requests.get(self.base_url, params=params, timeout=self.timeout_sec)
            r.raise_for_status()
            data = self._parse_response(r)
        except Exception:
            return None

        ghi = self._extract_ghi_times_best_effort(data)

        prof = SolarProfile(
            provider="KIER",
            fetched_at=time.time(),
            lat=lat_f,
            lon=lon_f,
            ghi_times=ghi,
            raw=data,
        )

        self._set_cache(cache_key, prof)
        return prof

    # ----------------
    # Cache
    # ----------------
    def _make_cache_key(
        self,
        lat: float,
        lon: float,
        when: Optional[str],
        extra_params: Optional[Dict[str, Any]],
    ) -> str:
        payload = {
            "base_url": self.base_url,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "when": when or "",
            "extra": extra_params or {},
        }
        s = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def _get_cache(self, key: str) -> Optional[SolarProfile]:
        v = self._cache.get(key)
        if not v:
            return None
        ts, prof = v
        if (time.time() - ts) > self.cache_ttl_sec:
            self._cache.pop(key, None)
            return None
        return prof

    def _set_cache(self, key: str, prof: SolarProfile) -> None:
        self._cache[key] = (time.time(), prof)

    # ----------------
    # Response parsing
    # ----------------
    def _parse_response(self, r: requests.Response) -> Dict[str, Any]:
        ct = (r.headers.get("Content-Type") or "").lower()
        text = r.text or ""

        # JSON 우선
        if "application/json" in ct or text.strip().startswith("{") or text.strip().startswith("["):
            try:
                return r.json()
            except Exception:
                return {"text": text, "content_type": ct}

        # XML일 수 있음 (공공데이터포털 흔함)
        if "xml" in ct or text.strip().startswith("<"):
            # xml을 dict로 완벽 변환은 추가 라이브러리 필요할 수 있어,
            # 여기서는 원문을 raw로 저장하고, 숫자 추출은 문자열 탐색으로 처리
            return {"xml": text, "content_type": ct}

        return {"text": text, "content_type": ct}

    # ----------------
    # GHI extraction (best effort)
    # ----------------
    def _extract_ghi_times_best_effort(self, data: Dict[str, Any]) -> Dict[str, float]:
        """
        목표: morning/noon/evening 3개 값으로 normalize해서 반환.

        - 명세를 알기 전이므로 "최대한" 찾아보고,
          못 찾으면 1.0/1.0/1.0을 반환(= Solar 미적용과 동일 동작 유도)
        """
        # 1) raw 전체에서 숫자 후보 찾기(딱 하나라도 찾으면 사용)
        numbers = self._find_numeric_values(data)

        # 2) 만약 time-series처럼 여러 개 있으면
        #    morning/noon/evening은 대충 3분할로 대표값 뽑기
        if len(numbers) >= 3:
            # 안정적으로 3개 대표값
            n = len(numbers)
            m = numbers[n // 6]           # 오전 대표
            no = numbers[n // 2]          # 정오 대표
            e = numbers[(5 * n) // 6]     # 저녁 대표
            return self._normalize_three(m, no, e)

        if len(numbers) == 2:
            return self._normalize_three(numbers[0], numbers[1], numbers[1])

        if len(numbers) == 1:
            return self._normalize_three(numbers[0], numbers[0], numbers[0])

        # 3) 완전 실패 → “영향 없음” 처리
        return {"morning": 1.0, "noon": 1.0, "evening": 1.0}

    def _normalize_three(self, a: float, b: float, c: float) -> Dict[str, float]:
        """
        값이 원단위(W/m^2 등)일 수도 있으니, 0~1로 안전 normalize.
        단, 전부 0이거나 음수면 1로 처리해서 시스템이 죽지 않게.
        """
        vals = [float(a), float(b), float(c)]
        vmax = max(vals)
        vmin = min(vals)

        # 원단위가 들어오면 보통 0~수백/천 단위.
        # normalize 기준: max로 나누기(상대값).
        if vmax <= 0:
            return {"morning": 1.0, "noon": 1.0, "evening": 1.0}

        # 변동이 너무 작으면(거의 동일) 그냥 1로
        if abs(vmax - vmin) < 1e-6:
            return {"morning": 1.0, "noon": 1.0, "evening": 1.0}

        return {
            "morning": float(vals[0] / vmax),
            "noon": float(vals[1] / vmax),
            "evening": float(vals[2] / vmax),
        }

    def _find_numeric_values(self, data: Any) -> list[float]:
        """
        data(dict/xml/text)에서 ghi 후보 키/값을 최대한 찾아 숫자 리스트 반환
        - JSON이면 키워드 기반으로 더 적극적으로 탐색
        - XML/text면 문자열에서 부동소수점/정수 숫자 패턴을 뽑음(너무 난잡하면 필터링)
        """
        out: list[float] = []

        def try_float(x: Any) -> Optional[float]:
            try:
                if isinstance(x, bool):
                    return None
                if x is None:
                    return None
                return float(str(x).strip())
            except Exception:
                return None

        def walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    lk = str(k).lower()
                    # 키에 ghi 후보가 들어가면 우선적으로 파싱
                    if any(key in lk for key in self.ghi_keys):
                        fv = try_float(v)
                        if fv is not None:
                            out.append(fv)
                    walk(v)
            elif isinstance(obj, list):
                for it in obj:
                    walk(it)
            elif isinstance(obj, (int, float)):
                out.append(float(obj))
            elif isinstance(obj, str):
                # XML/text이면 숫자 뽑기
                out.extend(self._extract_numbers_from_text(obj))

        walk(data)

        # 너무 많은 잡숫자가 들어오면 상위 범위만 필터링
        # (예: 타임스탬프 202601181200 같은 값이 섞일 수 있음)
        out2 = []
        for v in out:
            # 일사량은 대개 0~2000 정도. normalize 기반이니 넓게 허용.
            if 0 <= v <= 5000:
                out2.append(v)

        # 값이 하나도 없으면 out2도 비어있음
        return out2

    def _extract_numbers_from_text(self, s: str) -> list[float]:
        import re
        nums: list[float] = []

        # 소수/정수 추출
        for m in re.finditer(r"(-?\d+(?:\.\d+)?)", s):
            try:
                v = float(m.group(1))
                nums.append(v)
            except Exception:
                continue

        # 너무 많으면 중간값 위주로 샘플링 (성능/노이즈 방지)
        if len(nums) > 200:
            step = max(1, len(nums) // 200)
            nums = nums[::step]

        return nums
