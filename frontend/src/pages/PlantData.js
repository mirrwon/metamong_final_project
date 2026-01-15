import { useEffect, useMemo, useState } from 'react';
import api from '../services/api';

const buildImageUrl = (baseUrl, url) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (!baseUrl) return url;
  return `${baseUrl}${url}`;
};

const PlantData = () => {
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');

  const baseUrl = useMemo(() => api.defaults.baseURL || '', []);

  useEffect(() => {
    let active = true;

    const loadPlants = async () => {
      try {
        const { data } = await api.get('/api/plants');
        if (!active) return;
        const nextItems = Array.isArray(data?.items) ? data.items : [];
        setItems(nextItems);
        setError('');
      } catch (err) {
        if (!active) return;
        setItems([]);
        setError('Failed to load plant data.');
      }
    };

    loadPlants();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="l-cover">
      <div className="l-cover-center">
        <h1 className="typo-title">Plant Data</h1>
        <div className="ui-line" />

        {error ? <p>{error}</p> : null}
        {!error && items.length === 0 ? <p>No plants yet.</p> : null}

        <ul>
          {items.map((plant) => (
            <li key={plant.id || plant.name}>
              {plant.image ? (
                <img
                  src={buildImageUrl(baseUrl, plant.image)}
                  alt={plant.name}
                  loading="lazy"
                />
              ) : null}
              <h2>{plant.name}</h2>
              <p>Care: {plant.care}</p>
              <p>Allergy: {plant.allergy}</p>
              <p>Pet safe: {plant.pet_safe ? 'yes' : 'no'}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default PlantData;
