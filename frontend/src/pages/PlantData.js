import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';
import './PlantData.css';

const buildImageUrl = (baseUrl, url) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (!baseUrl) return url;
  return `${baseUrl}${url}`;
};

const PlantData = () => {
  const [allItems, setAllItems] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [pageIndex, setPageIndex] = useState(0);
  const [imageFailures, setImageFailures] = useState({});
  const [imageFallbackIndex, setImageFallbackIndex] = useState({});
  const [selectedImageByPlant, setSelectedImageByPlant] = useState({});
  const [query, setQuery] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterSize, setFilterSize] = useState('');
  const [filterPlacement, setFilterPlacement] = useState('');
  const [filterPetSafe, setFilterPetSafe] = useState('');
  const inFlightRef = useRef(false);

  const pageSize = 10;

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

  const getImageCandidates = useCallback((url) => {
    if (!url) return [];
    const [basePart, queryPart] = url.split('?');
    const query = queryPart ? `?${queryPart}` : '';
    const match = basePart.match(/^(.*?)(\.[a-z0-9]+)$/i);
    if (!match) return [url];
    const stem = match[1];
    const ext = match[2].toLowerCase();
    const candidates = [
      url,
      `${stem}.gif${query}`,
      `${stem}.jpg${query}`,
      `${stem}.png${query}`,
      `${stem}.jpeg${query}`,
    ];
    return Array.from(new Set(candidates.filter(Boolean))).filter((item) => item !== url || ext);
  }, []);

  const resolveImageUrl = useCallback(
    (url) => {
      const candidates = getImageCandidates(url);
      const idx = imageFallbackIndex[url] || 0;
      return {
        candidates,
        url: candidates[idx] || candidates[0] || '',
      };
    },
    [getImageCandidates, imageFallbackIndex]
  );

  const handleImageError = useCallback((url) => {
    if (!url) return;
    const candidates = getImageCandidates(url);
    if (candidates.length <= 1) {
      setImageFailures((prev) => (prev[url] ? prev : { ...prev, [url]: true }));
      return;
    }
    setImageFallbackIndex((prev) => {
      const current = prev[url] || 0;
      const next = current + 1;
      if (next >= candidates.length) {
        setImageFailures((failPrev) => (failPrev[url] ? failPrev : { ...failPrev, [url]: true }));
        return prev;
      }
      return { ...prev, [url]: next };
    });
  }, [getImageCandidates]);

  const loadAllPlants = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setLoading(true);
    setError('');
    try {
      const limit = 100;
      let offset = 0;
      let total = null;
      let merged = [];
      while (true) {
        const response = await api.get('/api/plants', {
          params: { offset, limit },
        });
        const nextItems = Array.isArray(response?.data?.items) ? response.data.items : [];
        merged = [...merged, ...nextItems];
        if (Number.isInteger(response?.data?.total)) {
          total = response.data.total;
        }
        if (nextItems.length < limit) break;
        if (total !== null && merged.length >= total) break;
        offset += limit;
      }
      setAllItems(merged);
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
      const name = String(plant?.name || '').toLowerCase();
      if (normalizedQuery && !name.includes(normalizedQuery)) return false;
      if (filterType && plant?.type !== filterType) return false;
      if (filterSize && plant?.size !== filterSize) return false;
      if (filterPetSafe) {
        if (filterPetSafe === 'yes' && plant?.pet_safe !== true) return false;
        if (filterPetSafe === 'no' && plant?.pet_safe !== false) return false;
        if (filterPetSafe === 'na' && plant?.pet_safe !== null) return false;
      }
      if (filterPlacement) {
        const placement = String(plant?.placement || '').toLowerCase();
        if (!placement.includes(filterPlacement.toLowerCase())) return false;
      }
      return true;
    });
  }, [allItems, filterPlacement, filterPetSafe, filterSize, filterType, normalizedQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const safePageIndex = Math.min(pageIndex, totalPages - 1);
  const pageWindowSize = 5;
  const pageWindowStart = Math.floor(safePageIndex / pageWindowSize) * pageWindowSize;
  const pageWindowEnd = Math.min(pageWindowStart + pageWindowSize, totalPages);

  useEffect(() => {
    setPageIndex(0);
  }, [normalizedQuery, filterType, filterSize, filterPlacement, filterPetSafe]);

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
    const prevStart = Math.max(0, pageWindowStart - pageWindowSize);
    setPageIndex(prevStart);
  };

  const handleNextWindow = () => {
    if (loading) return;
    const nextStart = Math.min(totalPages - 1, pageWindowStart + pageWindowSize);
    setPageIndex(nextStart);
  };

  const pageItems = useMemo(() => {
    const start = safePageIndex * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, safePageIndex, pageSize]);

  const typeOptions = useMemo(() => {
    const set = new Set();
    allItems.forEach((plant) => {
      if (plant?.type) set.add(plant.type);
    });
    return Array.from(set).sort();
  }, [allItems]);

  const sizeOptions = useMemo(() => {
    const set = new Set();
    allItems.forEach((plant) => {
      if (plant?.size) set.add(plant.size);
    });
    const preferred = ['소', '중', '대'];
    const values = Array.from(set);
    const ordered = preferred.filter((item) => values.includes(item));
    const rest = values.filter((item) => !preferred.includes(item)).sort();
    return [...ordered, ...rest];
  }, [allItems]);

  const placementOptions = useMemo(() => {
    const set = new Set();
    allItems.forEach((plant) => {
      const placement = String(plant?.placement || '');
      placement
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
        .forEach((item) => set.add(item));
    });
    return Array.from(set).sort();
  }, [allItems]);

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
        <h1 className="typo-title">식물 데이터</h1>
        <div className="ui-line" />

        {error ? <p className="catalog-status">식물 데이터를 불러오지 못했습니다.</p> : null}

        <div className="catalog-filters">
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
            <label htmlFor="plant-type">종류</label>
            <select
              id="plant-type"
              value={filterType}
              onChange={(event) => setFilterType(event.target.value)}
            >
              <option value="">전체</option>
              {typeOptions.map((type) => (
                <option value={type} key={type}>
                  {type}
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
              <option value="na">정보 없음</option>
            </select>
          </div>
          <button
            className="ui-btn ui-btn-ghost ui-btn--compact catalog-filter__reset"
            type="button"
            onClick={() => {
              setQuery('');
              setFilterType('');
              setFilterSize('');
              setFilterPlacement('');
              setFilterPetSafe('');
            }}
          >
            초기화
          </button>
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
                const visibleImages = images.filter((url) => !imageFailures[url]);
                const selected = selectedImageByPlant[plantKey];
                const displayImage = visibleImages.includes(selected)
                  ? selected
                  : visibleImages[0];
                const resolvedMain = resolveImageUrl(displayImage);

                if (!displayImage) {
                  return <div className="catalog-image catalog-image--placeholder" />;
                }

                return (
                  <div className="catalog-image-stack">
                    <img
                      className="catalog-image"
                      src={resolvedMain.url}
                      alt={plant.name}
                      loading="lazy"
                      onError={() => handleImageError(displayImage)}
                    />
                    {visibleImages.length > 1 ? (
                      <div className="catalog-thumbs">
                        {visibleImages.map((url, index) => {
                          const resolvedThumb = resolveImageUrl(url);
                          return (
                          <button
                            className={`catalog-thumb${
                              url === displayImage ? ' is-active' : ''
                            }`}
                            type="button"
                            key={`${plantKey}-thumb-${index}`}
                            onClick={() =>
                              setSelectedImageByPlant((prev) => ({
                                ...prev,
                                [plantKey]: url,
                              }))
                            }
                          >
                            <img
                              src={resolvedThumb.url}
                              alt={`${plant.name} thumbnail ${index + 1}`}
                              loading="lazy"
                              onError={() => handleImageError(url)}
                            />
                          </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })()}
              <header className="catalog-header">
                <h2 className="catalog-title">{plant.name}</h2>
              </header>
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
                <p>
                  반려동물 안전:{' '}
                  {plant.pet_safe === null ? '정보 없음' : plant.pet_safe ? '안전' : '주의'}
                </p>
                {plant.type ? <span className="catalog-chip">{plant.type}</span> : null}
              </div>
            </article>
          ))}
        </div>
        {loading ? <p className="catalog-status">식물 정보를 불러오는 중...</p> : null}
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
      </div>
    </div>
  );
};

export default PlantData;
