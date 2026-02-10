import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';
import './PlantData.css';

const PAGE_SIZE = 10;
const PAGE_WINDOW_SIZE = 5;
const LIGHT_ORDER = ['낮은 광도', '중간 광도', '높은 광도'];
const CARE_ORDER = ['쉬움', '보통', '어려움'];
const SIZE_ORDER = ['소', '중', '대'];
const KID_SAFETY_ORDER = ['대체로 안전', '주의', '비권장'];

const buildImageUrl = (baseUrl, url) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (!baseUrl) return url;
  return `${baseUrl}${url}`;
};

const toArray = (value) => (Array.isArray(value) ? value : value ? [value] : []);

const getOrderedUniqueValues = (items, getValues, preferred = []) => {
  const set = new Set();
  items.forEach((item) => toArray(getValues(item)).forEach((value) => value && set.add(value)));
  const values = Array.from(set);
  if (!preferred.length) return values.sort();
  const ordered = preferred.filter((value) => values.includes(value));
  const rest = values.filter((value) => !preferred.includes(value)).sort();
  return [...ordered, ...rest];
};

const matchesFilterValue = (selected, current) => !selected || String(current || '') === selected;

const parsePhotoCount = (plant) => {
  const raw = plant?.photo_count ?? plant?.attrs?.photo_count;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return null;
  return parsed;
};

const PlantData = () => {
  const [allItems, setAllItems] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [pageIndex, setPageIndex] = useState(0);
  const [imageFailures, setImageFailures] = useState({});
  const [selectedImageByPlant, setSelectedImageByPlant] = useState({});
  const [query, setQuery] = useState('');
  const [filterLight, setFilterLight] = useState('');
  const [filterCare, setFilterCare] = useState('');
  const [filterSize, setFilterSize] = useState('');
  const [filterPlacement, setFilterPlacement] = useState('');
  const [filterPetSafe, setFilterPetSafe] = useState('');
  const [filterKidSafe, setFilterKidSafe] = useState('');
  const inFlightRef = useRef(false);

  const baseUrl = useMemo(() => api.defaults.baseURL || '', []);

  const getPlantImages = useCallback(
    (plant) => {
      if (!plant) return [];
      const images = Array.isArray(plant.images) ? plant.images : [];
      const primary = plant.image ? [plant.image] : [];
      const merged = [...primary, ...images];
      const normalized = merged
        .map((url) => buildImageUrl(baseUrl, url))
        .filter((url) => Boolean(url));
      return Array.from(new Set(normalized));
    },
    [baseUrl]
  );

  const handleImageError = useCallback((url) => {
    if (!url) return;
    setImageFailures((prev) => (prev[url] ? prev : { ...prev, [url]: true }));
  }, []);

  const handleShiftPlantImage = useCallback((plantKey, images, delta) => {
    if (!plantKey || !Array.isArray(images) || images.length <= 1) return;
    setSelectedImageByPlant((prev) => {
      const selected = prev[plantKey];
      const currentIndex = Math.max(0, images.indexOf(selected));
      const nextIndex = (currentIndex + delta + images.length) % images.length;
      return { ...prev, [plantKey]: images[nextIndex] };
    });
  }, []);

  const loadAllPlants = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setLoading(true);
    setError('');
    try {
      const cacheKey = 'plantDataCache_v1';
      const cacheTtlMs = 1000 * 60 * 10;
      const readCache = () => {
        try {
          const raw = window.localStorage.getItem(cacheKey);
          if (!raw) return null;
          const parsed = JSON.parse(raw);
          if (!parsed?.ts || !Array.isArray(parsed?.items)) return null;
          if (Date.now() - parsed.ts > cacheTtlMs) return null;
          return parsed.items;
        } catch {
          return null;
        }
      };
      const writeCache = (items) => {
        try {
          window.localStorage.setItem(
            cacheKey,
            JSON.stringify({ ts: Date.now(), items })
          );
        } catch {
          // ignore storage errors
        }
      };

      const cached = readCache();
      if (cached && cached.length) {
        setAllItems(cached);
      }

      const limit = 100;
      const firstResponse = await api.get('/api/plants', {
        params: { offset: 0, limit },
      });
      const firstItems = Array.isArray(firstResponse?.data?.items) ? firstResponse.data.items : [];
      const total = Number.isInteger(firstResponse?.data?.total)
        ? firstResponse.data.total
        : firstItems.length;

      let merged = [...firstItems];
      if (total > limit) {
        const offsets = [];
        for (let offset = limit; offset < total; offset += limit) {
          offsets.push(offset);
        }
        const chunkResponses = await Promise.all(
          offsets.map((offset) =>
            api.get('/api/plants', {
              params: { offset, limit },
            })
          )
        );
        chunkResponses.forEach((response) => {
          const nextItems = Array.isArray(response?.data?.items) ? response.data.items : [];
          merged = [...merged, ...nextItems];
        });
      }
      setAllItems(merged);
      writeCache(merged);
    } catch (err) {
      setError('Failed to load plant data.');
      setAllItems([]);
    } finally {
      setLoading(false);
      inFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    loadAllPlants();
  }, [loadAllPlants]);

  const normalizedQuery = useMemo(() => query.trim().toLowerCase(), [query]);
  const filteredItems = useMemo(() => {
    return allItems.filter((plant) => {
      if (normalizedQuery && !String(plant?.name || '').toLowerCase().includes(normalizedQuery)) return false;
      if (filterLight && !toArray(plant?.light_requirement).includes(filterLight)) return false;
      if (!matchesFilterValue(filterCare, plant?.care)) return false;
      if (!matchesFilterValue(filterSize, plant?.size)) return false;
      if (filterPetSafe && (filterPetSafe === 'yes') !== (plant?.pet_safe === true)) return false;
      if (!matchesFilterValue(filterKidSafe, plant?.attrs?.kid_safety_grade)) return false;
      if (filterPlacement) return String(plant?.placement || '').toLowerCase().includes(filterPlacement.toLowerCase());
      return true;
    });
  }, [
    allItems,
    filterCare,
    filterKidSafe,
    filterLight,
    filterPlacement,
    filterPetSafe,
    filterSize,
    normalizedQuery,
  ]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE));
  const safePageIndex = Math.min(pageIndex, totalPages - 1);
  const pageWindowStart = Math.floor(safePageIndex / PAGE_WINDOW_SIZE) * PAGE_WINDOW_SIZE;
  const pageWindowEnd = Math.min(pageWindowStart + PAGE_WINDOW_SIZE, totalPages);

  useEffect(() => {
    setPageIndex(0);
  }, [normalizedQuery, filterLight, filterCare, filterSize, filterPlacement, filterPetSafe, filterKidSafe]);

  useEffect(() => {
    if (pageIndex !== safePageIndex) {
      setPageIndex(safePageIndex);
    }
  }, [pageIndex, safePageIndex]);

  const handleNext = () => {
    if (loading) return;
    setPageIndex((prev) => Math.min(prev + 1, totalPages - 1));
  };

  const handlePrev = () => {
    if (loading) return;
    setPageIndex((prev) => Math.max(prev - 1, 0));
  };

  const handleJump = (index) => {
    if (loading) return;
    setPageIndex(index);
  };

  const handlePrevWindow = () => {
    if (loading) return;
    const prevStart = Math.max(0, pageWindowStart - PAGE_WINDOW_SIZE);
    setPageIndex(prevStart);
  };

  const handleNextWindow = () => {
    if (loading) return;
    const nextStart = Math.min(totalPages - 1, pageWindowStart + PAGE_WINDOW_SIZE);
    setPageIndex(nextStart);
  };

  const pageItems = useMemo(() => {
    const start = safePageIndex * PAGE_SIZE;
    return filteredItems.slice(start, start + PAGE_SIZE);
  }, [filteredItems, safePageIndex]);

  const lightOptions = useMemo(
    () => getOrderedUniqueValues(allItems, (plant) => plant?.light_requirement, LIGHT_ORDER),
    [allItems]
  );

  const careOptions = useMemo(
    () => getOrderedUniqueValues(allItems, (plant) => plant?.care, CARE_ORDER),
    [allItems]
  );

  const sizeOptions = useMemo(
    () => getOrderedUniqueValues(allItems, (plant) => plant?.size, SIZE_ORDER),
    [allItems]
  );

  const placementOptions = useMemo(() => {
    return getOrderedUniqueValues(allItems, (plant) =>
      String(plant?.placement || '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
    );
  }, [allItems]);

  const kidSafetyOptions = useMemo(
    () => getOrderedUniqueValues(allItems, (plant) => plant?.attrs?.kid_safety_grade, KID_SAFETY_ORDER),
    [allItems]
  );

  const clearAllFilters = useCallback(() => {
    setQuery('');
    setFilterLight('');
    setFilterCare('');
    setFilterSize('');
    setFilterPlacement('');
    setFilterPetSafe('');
    setFilterKidSafe('');
  }, []);

  if (loading) {
    return (
      <div className="l-cover plantdata-page">
        <div className="catalog-loading">
          <p className="typo-title">불러오는 중...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="l-cover plantdata-page">
      <div className="l-cover-center plantdata-center">
        <header className="catalog-topbar">
          <div>
            <h1 className="typo-title">식물 데이터</h1>
            <p className="catalog-subtitle">공간에 맞는 식물을 빠르게 찾아보세요.</p>
          </div>
        </header>
        <div className="ui-line" />

        {error ? <p className="catalog-status">식물 데이터를 불러오지 못했습니다.</p> : null}

        <div className="catalog-filters" role="region" aria-label="식물 필터">
          <div className="catalog-filter">
            <label htmlFor="plant-search">검색</label>
            <input
              id="plant-search"
              type="search"
              value={query}
              placeholder="이름으로 검색"
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <div className="catalog-filter">
            <label htmlFor="plant-light">광량</label>
            <select
              id="plant-light"
              value={filterLight}
              onChange={(event) => setFilterLight(event.target.value)}
            >
              <option value="">전체</option>
              {lightOptions.map((light) => (
                <option value={light} key={light}>
                  {light}
                </option>
              ))}
            </select>
          </div>
          <div className="catalog-filter">
            <label htmlFor="plant-care">관리 난이도</label>
            <select
              id="plant-care"
              value={filterCare}
              onChange={(event) => setFilterCare(event.target.value)}
            >
              <option value="">전체</option>
              {careOptions.map((care) => (
                <option value={care} key={care}>
                  {care}
                </option>
              ))}
            </select>
          </div>
          <div className="catalog-filter">
            <label htmlFor="plant-size">크기</label>
            <select
              id="plant-size"
              value={filterSize}
              onChange={(event) => setFilterSize(event.target.value)}
            >
              <option value="">전체</option>
              {sizeOptions.map((size) => (
                <option value={size} key={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>
          <div className="catalog-filter">
            <label htmlFor="plant-placement">배치 공간</label>
            <select
              id="plant-placement"
              value={filterPlacement}
              onChange={(event) => setFilterPlacement(event.target.value)}
            >
              <option value="">전체</option>
              {placementOptions.map((placement) => (
                <option value={placement} key={placement}>
                  {placement}
                </option>
              ))}
            </select>
          </div>
          <div className="catalog-filter">
            <label htmlFor="plant-petsafe">반려동물 안전</label>
            <select
              id="plant-petsafe"
              value={filterPetSafe}
              onChange={(event) => setFilterPetSafe(event.target.value)}
            >
              <option value="">전체</option>
              <option value="yes">안전</option>
              <option value="no">주의</option>
            </select>
          </div>
          <div className="catalog-filter">
            <label htmlFor="plant-kidsafe">어린이 안전</label>
            <select
              id="plant-kidsafe"
              value={filterKidSafe}
              onChange={(event) => setFilterKidSafe(event.target.value)}
            >
              <option value="">전체</option>
              {kidSafetyOptions.map((value) => (
                <option value={value} key={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <button
            className="ui-btn ui-btn-ghost ui-btn--compact catalog-filter__reset"
            type="button"
            onClick={clearAllFilters}
          >
            초기화
          </button>
          <div className="catalog-filters-meta">
            <span>전체 {allItems.length}개</span>
            <span>검색 결과 {filteredItems.length}개</span>
          </div>
        </div>

        {!error && pageItems.length === 0 && !loading ? (
          <p className="catalog-status">등록된 식물이 없습니다.</p>
        ) : null}

        <div className="catalog-grid">
          {pageItems.map((plant) => (
            <article className="catalog-card" key={plant.id || plant.name}>
              {(() => {
                const plantKey = plant.id || plant.name;
                const images = getPlantImages(plant);
                const photoCount = parsePhotoCount(plant);
                const uiImages = photoCount ? images.slice(0, photoCount) : images;
                const visibleImages = uiImages.filter((url) => !imageFailures[url]);
                const selected = selectedImageByPlant[plantKey];
                const displayImage = visibleImages.includes(selected) ? selected : visibleImages[0];
                const displayIndex = Math.max(0, uiImages.indexOf(displayImage));

                if (!displayImage) {
                  return <div className="catalog-image catalog-image--placeholder" />;
                }

                return (
                  <div className="catalog-image-stack">
                    <img
                      className="catalog-image"
                      src={displayImage}
                      alt={plant.name}
                      loading="lazy"
                      onError={() => handleImageError(displayImage)}
                    />
                    {visibleImages.length > 1 ? (
                      <div className="catalog-image-nav">
                        <button
                          className="catalog-image-nav-btn"
                          type="button"
                          onClick={() => handleShiftPlantImage(plantKey, uiImages, -1)}
                          aria-label={`${plant.name} 이전 사진`}
                        >
                          ‹
                        </button>
                        <span className="catalog-image-nav-status">
                          {displayIndex + 1} / {uiImages.length}
                        </span>
                        <button
                          className="catalog-image-nav-btn"
                          type="button"
                          onClick={() => handleShiftPlantImage(plantKey, uiImages, 1)}
                          aria-label={`${plant.name} 다음 사진`}
                        >
                          ›
                        </button>
                      </div>
                    ) : null}
                    {uiImages.length > 1 ? (
                      <div className="catalog-image-dots">
                        {uiImages.map((url, index) => (
                          <button
                            className={`catalog-image-dot${
                              url === displayImage ? ' is-active' : ''
                            }`}
                            type="button"
                            key={`${plantKey}-dot-${index}`}
                            onClick={() =>
                              setSelectedImageByPlant((prev) => ({
                                ...prev,
                                [plantKey]: url,
                              }))
                            }
                            aria-label={`${plant.name} 사진 ${index + 1}`}
                            disabled={imageFailures[url]}
                          >
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })()}
              <header className="catalog-header">
                <h2 className="catalog-title">{plant.name}</h2>
              </header>
              <div className="catalog-badges">
                <span className={`catalog-badge ${plant.pet_safe ? 'is-safe' : 'is-caution'}`}>
                  반려동물 {plant.pet_safe ? '안전' : '주의'}
                </span>
                <span
                  className={`catalog-badge ${
                    String(plant?.attrs?.kid_safety_grade || '') === '대체로 안전'
                      ? 'is-safe'
                      : 'is-caution'
                  }`}
                >
                  어린이 {plant?.attrs?.kid_safety_grade || '정보없음'}
                </span>
              </div>
              <div className="catalog-meta">
                <p>크기: {plant.size || '정보 없음'}</p>
                <p>
                  광량: {plant.light_min || '정보 없음'}
                  {plant.light_max ? ` - ${plant.light_max}` : ''}
                </p>
                <p>배치: {plant.placement || '정보 없음'}</p>
              </div>
              <div className="catalog-details">
                <p>관리 난이도: {plant.care || '정보 없음'}</p>
                <p>알러지: {plant.allergy || '정보 없음'}</p>
                {plant.type ? <span className="catalog-chip">{plant.type}</span> : null}
              </div>
            </article>
          ))}
        </div>
        {loading ? <p className="catalog-status">식물 정보를 불러오는 중...</p> : null}
        {totalPages > 1 ? (
        <div className="catalog-pagination catalog-pagination--numbers">
          <button
            className="ui-btn ui-btn-ghost ui-btn--compact"
            type="button"
            onClick={handlePrev}
            disabled={loading || safePageIndex === 0}
          >
            이전
          </button>
          <button
            className="catalog-page-btn catalog-page-btn--arrow"
            type="button"
            onClick={handlePrevWindow}
            disabled={loading || pageWindowStart === 0}
            aria-label="이전 5페이지"
          >
            ‹
          </button>
          <div className="catalog-page-list">
            {Array.from(
              { length: pageWindowEnd - pageWindowStart },
              (_, offset) => pageWindowStart + offset
            ).map((index) => (
              <button
                key={`page-${index}`}
                type="button"
                className={`catalog-page-btn${index === safePageIndex ? ' is-active' : ''}`}
                onClick={() => handleJump(index)}
                disabled={loading}
              >
                {index + 1}
              </button>
            ))}
          </div>
          <button
            className="catalog-page-btn catalog-page-btn--arrow"
            type="button"
            onClick={handleNextWindow}
            disabled={loading || pageWindowEnd >= totalPages}
            aria-label="다음 5페이지"
          >
            ›
          </button>
          <button
            className="ui-btn ui-btn-primary ui-btn--compact"
            type="button"
            onClick={handleNext}
            disabled={loading || safePageIndex >= totalPages - 1}
          >
            다음
          </button>
        </div>
        ) : null}
      </div>
    </div>
  );
};

export default PlantData;
