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
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageCache, setPageCache] = useState({});
  const [total, setTotal] = useState(null);
  const [prefetching, setPrefetching] = useState(false);
  const inFlightRef = useRef(false);
  const pageCacheRef = useRef({});

  const pageSize = 10;

  const baseUrl = useMemo(() => api.defaults.baseURL || '', []);

  const loadPlants = useCallback(
    async (index, { showLoading } = { showLoading: false }) => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;

      const cachedPage = pageCacheRef.current[index];
      if (cachedPage) {
        if (showLoading) {
          setLoading(true);
          setItems([]);
          setTimeout(() => {
            setItems(cachedPage);
            setError('');
            setLoading(false);
            inFlightRef.current = false;
          }, 0);
          return;
        }
        setItems(cachedPage);
        setError('');
        inFlightRef.current = false;
        return;
      }
      const offset = index * pageSize;
      if (showLoading) {
        setItems([]);
      }
      setLoading(true);
      try {
        const response = await api.get('/api/plants', {
          params: {
            offset,
            limit: pageSize,
          },
        });
        const nextItems = Array.isArray(response?.data?.items) ? response.data.items : [];
        setItems(nextItems);
        setPageCache((prev) => {
          const updated = { ...prev, [index]: nextItems };
          pageCacheRef.current = updated;
          return updated;
        });
        setTotal(Number.isInteger(response?.data?.total) ? response.data.total : null);
        setError('');
      } catch (err) {
        setError('Failed to load plant data.');
      } finally {
        setLoading(false);
        inFlightRef.current = false;
      }
    },
    [pageSize]
  );

  const prefetchPlants = useCallback(
    async (index) => {
      if (prefetching || pageCacheRef.current[index]) return;
      const offset = index * pageSize;
      setPrefetching(true);
      try {
        const response = await api.get('/api/plants', {
          params: {
            offset,
            limit: pageSize,
          },
        });
        const nextItems = Array.isArray(response?.data?.items) ? response.data.items : [];
        setPageCache((prev) => {
          const updated = { ...prev, [index]: nextItems };
          pageCacheRef.current = updated;
          return updated;
        });
        setTotal(Number.isInteger(response?.data?.total) ? response.data.total : null);
      } finally {
        setPrefetching(false);
      }
    },
    [pageSize, prefetching]
  );

  useEffect(() => {
    loadPlants(0, { showLoading: true });
  }, [loadPlants]);

  useEffect(() => {
    if (total !== null && (pageIndex + 1) * pageSize >= total) return;
    prefetchPlants(pageIndex + 1);
  }, [pageIndex, pageSize, prefetchPlants, total]);

  const handleNext = () => {
    if (loading) return;
    const nextIndex = pageIndex + 1;
    setPageIndex(nextIndex);
    loadPlants(nextIndex, { showLoading: true });
  };

  const handlePrev = () => {
    if (loading || pageIndex === 0) return;
    const prevIndex = pageIndex - 1;
    setPageIndex(prevIndex);
    loadPlants(prevIndex, { showLoading: true });
  };

  const canGoNext =
    !loading &&
    (pageCache[pageIndex + 1] || total === null || (pageIndex + 1) * pageSize < total);

  if (loading) {
    return (
      <div className="l-cover plantdata-page">
        <div className="catalog-loading">
          <p className="typo-title">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="l-cover plantdata-page">
      <div className="l-cover-center plantdata-center">
        <h1 className="typo-title">Plant Data</h1>
        <div className="ui-line" />

        {error ? <p className="catalog-status">{error}</p> : null}
        {!error && items.length === 0 && !loading ? (
          <p className="catalog-status">No plants yet.</p>
        ) : null}

        <div className="catalog-grid">
          {items.map((plant) => (
            <article className="catalog-card" key={plant.id || plant.name}>
              {plant.image ? (
                <img
                  className="catalog-image"
                  src={buildImageUrl(baseUrl, plant.image)}
                  alt={plant.name}
                  loading="lazy"
                />
              ) : (
                <div className="catalog-image catalog-image--placeholder" />
              )}
              <header className="catalog-header">
                <h2 className="catalog-title">{plant.name}</h2>
              </header>
              <div className="catalog-meta">
                <p>Size: {plant.size || 'n/a'}</p>
                <p>
                  Light: {plant.light_min || 'n/a'}
                  {plant.light_max ? ` - ${plant.light_max}` : ''}
                </p>
                <p>Placement: {plant.placement || 'n/a'}</p>
              </div>
              <div className="catalog-details">
                <p>Care: {plant.care || 'n/a'}</p>
                <p>Allergy: {plant.allergy || 'n/a'}</p>
                <p>
                  Pet safe:{' '}
                  {plant.pet_safe === null ? 'n/a' : plant.pet_safe ? 'yes' : 'no'}
                </p>
                {plant.type ? <span className="catalog-chip">{plant.type}</span> : null}
              </div>
            </article>
          ))}
        </div>
        {loading ? <p className="catalog-status">Loading plants...</p> : null}
        <div className="catalog-pagination">
          <button
            className="ui-btn ui-btn-ghost ui-btn--compact"
            type="button"
            onClick={handlePrev}
            disabled={loading || pageIndex === 0}
          >
            Previous
          </button>
          <span className="catalog-page">Page {pageIndex + 1}</span>
          <button
            className="ui-btn ui-btn-primary ui-btn--compact"
            type="button"
            onClick={handleNext}
            disabled={!canGoNext}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
};

export default PlantData;
