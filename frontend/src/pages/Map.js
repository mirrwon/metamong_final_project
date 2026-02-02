import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "../services/api";
import { readStoredUser } from "../services/session";
import "./Map.css";

const DEFAULT_RADIUS = 3000;

const formatDistance = (value) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "";
  if (parsed >= 1000) {
    const km = (parsed / 1000).toFixed(parsed >= 10000 ? 0 : 1);
    return `${km}km`;
  }
  return `${Math.round(parsed)}m`;
};

const resolveErrorMessage = (error) => {
  const detail = error?.response?.data?.detail;
  if (detail) {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((item) => item?.msg).filter(Boolean).join(" ");
    }
  }
  return "꽃집 정보를 불러오지 못했어요.";
};

const MapPage = () => {
  const [shops, setShops] = useState([]);
  const [address, setAddress] = useState("");
  const [coord, setCoord] = useState(null);
  const [error, setError] = useState("");
  const [mapError, setMapError] = useState("");
  const [loading, setLoading] = useState(false);

  const storedUser = useMemo(() => readStoredUser(), []);
  const username = storedUser?.user_name || storedUser?.username || "";
  const kakaoKey = useMemo(() => process.env.REACT_APP_KAKAO_JS_KEY || "", []);
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);
  const markerByKeyRef = useRef(new Map());
  const infoWindowRef = useRef(null);
  const kakaoLoaderRef = useRef(null);
  const focusTimerRef = useRef(null);

  const getShopKey = useCallback((shop) => {
    if (!shop) return "";
    return (
      shop.id ||
      `${shop.name || ""}|${shop.address || ""}|${shop.x || ""}|${shop.y || ""}`
    );
  }, []);

  const loadKakaoSdk = useCallback(() => {
    if (window.kakao && window.kakao.maps) {
      return Promise.resolve(window.kakao);
    }
    if (!kakaoKey) {
      return Promise.reject(new Error("missing_kakao_key"));
    }
    if (kakaoLoaderRef.current) return kakaoLoaderRef.current;

    kakaoLoaderRef.current = new Promise((resolve, reject) => {
      const existing = document.getElementById("kakao-map-sdk");
      if (existing) {
        existing.addEventListener("load", () => {
          if (window.kakao && window.kakao.maps) {
            window.kakao.maps.load(() => resolve(window.kakao));
          } else {
            reject(new Error("kakao_sdk_unavailable"));
          }
        });
        existing.addEventListener("error", () => reject(new Error("kakao_sdk_load_failed")));
        return;
      }

      const script = document.createElement("script");
      script.id = "kakao-map-sdk";
      script.async = true;
      script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${kakaoKey}&autoload=false`;
      script.onload = () => {
        if (window.kakao && window.kakao.maps) {
          window.kakao.maps.load(() => resolve(window.kakao));
        } else {
          reject(new Error("kakao_sdk_unavailable"));
        }
      };
      script.onerror = () => reject(new Error("kakao_sdk_load_failed"));
      document.head.appendChild(script);
    });

    return kakaoLoaderRef.current;
  }, [kakaoKey]);

  const fetchShops = useCallback(async () => {
    if (!username) {
      setError("로그인 정보를 찾을 수 없어요.");
      setShops([]);
      setAddress("");
      setCoord(null);
      return;
    }

    setLoading(true);
    setError("");

    try {
      const response = await api.get("/api/map/flowers", {
        params: { username, radius: DEFAULT_RADIUS, include_parking: true },
      });

      const payload = response?.data;
      if (!payload?.ok) {
        setError("꽃집 정보를 불러오지 못했어요.");
        setShops([]);
        setAddress("");
        return;
      }

      setShops(Array.isArray(payload.items) ? payload.items : []);
      setAddress(payload.address || "");
      if (payload?.coord?.x && payload?.coord?.y) {
        setCoord({
          x: Number(payload.coord.x),
          y: Number(payload.coord.y),
        });
      } else {
        setCoord(null);
      }
    } catch (err) {
      setError(resolveErrorMessage(err));
      setShops([]);
      setAddress("");
      setCoord(null);
    } finally {
      setLoading(false);
    }
  }, [username]);

  useEffect(() => {
    fetchShops();
  }, [fetchShops]);

  const focusShopOnMap = useCallback(
    (shop) => {
      if (!shop) return;
      const key = getShopKey(shop);
      if (!key) return;

      loadKakaoSdk()
        .then((kakao) => {
          const map = mapRef.current;
          const entry = markerByKeyRef.current.get(key);
          if (!map || !entry?.marker) return;

          const { marker, shop: entryShop } = entry;
          const position = marker.getPosition();

          if (focusTimerRef.current) {
            clearTimeout(focusTimerRef.current);
            focusTimerRef.current = null;
          }

          map.panTo(position);

          const name = entryShop?.name || "꽃집";
          const address = entryShop?.road_address || entryShop?.address || "";
          const content = `
            <div style="padding:6px 8px;font-size:12px;line-height:1.4;">
              <strong>${name}</strong><br />
              ${address}
            </div>
          `;

          if (!infoWindowRef.current) {
            infoWindowRef.current = new kakao.maps.InfoWindow({ zIndex: 1 });
          }
          infoWindowRef.current.setContent(content);
          infoWindowRef.current.open(map, marker);

          const baseImage = marker.getImage();
          if (baseImage) {
            marker.setZIndex(10);
            focusTimerRef.current = setTimeout(() => {
              marker.setZIndex(0);
            }, 1200);
          }
        })
        .catch(() => {
          setMapError("지도에서 위치를 표시하지 못했어요.");
        });
    },
    [getShopKey, loadKakaoSdk]
  );

  useEffect(() => {
    if (!coord || !mapContainerRef.current) return;

    let cancelled = false;

    loadKakaoSdk()
      .then((kakao) => {
        if (cancelled || !mapContainerRef.current) return;
        setMapError("");

        const center = new kakao.maps.LatLng(coord.y, coord.x);
        if (!mapRef.current) {
          mapRef.current = new kakao.maps.Map(mapContainerRef.current, {
            center,
            level: 4,
          });
        } else {
          mapRef.current.setCenter(center);
        }

        markersRef.current.forEach((marker) => marker.setMap(null));
        markersRef.current = [];
        markerByKeyRef.current = new Map();

        const bounds = new kakao.maps.LatLngBounds();
        bounds.extend(center);

        const homeMarker = new kakao.maps.Marker({
          position: center,
          map: mapRef.current,
          title: "내 위치",
        });
        markersRef.current.push(homeMarker);

        if (!infoWindowRef.current) {
          infoWindowRef.current = new kakao.maps.InfoWindow({ zIndex: 1 });
        }

        shops.forEach((shop) => {
          const lat = Number(shop?.y);
          const lng = Number(shop?.x);
          if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

          const position = new kakao.maps.LatLng(lat, lng);
          bounds.extend(position);

          const marker = new kakao.maps.Marker({
            position,
            map: mapRef.current,
            title: shop?.name || "",
          });

          kakao.maps.event.addListener(marker, "click", () => {
            const name = shop?.name || "꽃집";
            const address = shop?.road_address || shop?.address || "";
            const content = `
              <div style="padding:6px 8px;font-size:12px;line-height:1.4;">
                <strong>${name}</strong><br />
                ${address}
              </div>
            `;
            infoWindowRef.current?.setContent(content);
            infoWindowRef.current?.open(mapRef.current, marker);
          });

          markersRef.current.push(marker);
          const shopKey = getShopKey(shop);
          if (shopKey) {
            markerByKeyRef.current.set(shopKey, { marker, shop });
          }
        });

        if (shops.length > 0) {
          mapRef.current.setBounds(bounds);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        if (err?.message === "missing_kakao_key") {
          setMapError("Kakao 지도 키가 필요합니다. 프론트엔드 .env에 설정해주세요.");
        } else {
          setMapError("Kakao 지도를 불러오지 못했어요.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [coord, loadKakaoSdk, shops]);

  return (
    <div className="l-cover map-page">
      <div className="l-cover-center map-center">
        <h1 className="map-title typo-title">내 주변 꽃집</h1>
        <div className="ui-line map-divider" />

        <section className="map-panel">
          <div className="map-info">
            <p className="map-label">기준 주소</p>
            <p className="map-address">
              {address || "등록된 주소가 없습니다."}
            </p>
            <p className="map-radius">검색 범위: 반경 3km</p>
          </div>
          <div className="map-actions">
            <button
              type="button"
              className="ui-btn ui-btn-primary ui-btn--compact map-refresh"
              onClick={fetchShops}
              disabled={loading}
            >
              다시 검색
            </button>
          </div>
        </section>

        <section className="map-canvas-wrap">
          {mapError ? <p className="map-error">{mapError}</p> : null}
          {!coord && !error ? (
            <p className="map-status">주소 좌표를 불러오지 못했어요.</p>
          ) : null}
          <div ref={mapContainerRef} className="map-canvas" />
        </section>

        {loading ? <p className="map-status">불러오는 중...</p> : null}
        {error ? <p className="map-error">{error}</p> : null}
        {!loading && !error && shops.length === 0 ? (
          <p className="map-status">주변에서 꽃집을 찾지 못했어요.</p>
        ) : null}

        <div className="map-grid">
          {shops.map((shop) => {
            const distanceLabel = formatDistance(shop?.distance);
            const primaryAddress = shop?.road_address || shop?.address || "";
            const parking = shop?.parking;
            const parkingName = parking?.name || "정보 없음";
            const parkingDistance = parking?.distance
              ? formatDistance(parking.distance)
              : "정보 없음";
            const parkingAddress =
              parking?.road_address || parking?.address || "";
            return (
              <article
                className="map-card"
                key={getShopKey(shop)}
                role="button"
                tabIndex={0}
                onClick={() => focusShopOnMap(shop)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    focusShopOnMap(shop);
                  }
                }}
              >
                <header className="map-card__header">
                  <h2 className="map-card__title">{shop?.name}</h2>
                  {distanceLabel ? (
                    <span className="map-card__distance">{distanceLabel}</span>
                  ) : null}
                </header>
                {primaryAddress ? (
                  <p className="map-card__address">{primaryAddress}</p>
                ) : null}
                {shop?.phone ? (
                  <p className="map-card__meta">전화: {shop.phone}</p>
                ) : null}
                <p className="map-card__meta">인근 주차장: {parkingName}</p>
                <p className="map-card__meta">
                  주차장부터의 거리: {parkingDistance}
                </p>
                {parkingAddress ? (
                  <p className="map-card__meta">주차장 주소: {parkingAddress}</p>
                ) : null}
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default MapPage;
