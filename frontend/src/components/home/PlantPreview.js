import { useEffect, useMemo, useState } from "react";
import api from "../../services/api";


const buildImageUrl = (baseUrl, url) => {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  if (!baseUrl) return url;
  return `${baseUrl}${url}`;
};

const PlantPreview = () => {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");

  const baseUrl = useMemo(() => api.defaults.baseURL || "", []);

  useEffect(() => {
    const fetchPlants = async () => {
      try {
        const res = await api.get("/api/plants", {
          params: { offset: 0, limit: 6 },
        });

        setItems(Array.isArray(res?.data?.items) ? res.data.items : []);
      } catch {
        setError("Failed to load plants.");
      }
    };

    fetchPlants();
  }, []);

  if (error) return <p className="catalog-status">{error}</p>;

  return (
    <div className="plant-preview-grid">
      {items.map((plant) => (
        <article key={plant.id || plant.name} className="plant-preview-card">
          {plant.image ? (
            <img
              src={buildImageUrl(baseUrl, plant.image)}
              alt={plant.name}
              className="plant-preview-image"
              loading="lazy"
            />
          ) : (
            <div className="plant-preview-image plant-preview-image--placeholder" />
          )}
          <p className="plant-preview-name">{plant.name}</p>
        </article>
      ))}
    </div>
  );
};

export default PlantPreview;
