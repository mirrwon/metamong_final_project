import { useCallback, useEffect, useState } from "react";
import { fetchWithSession } from "../services/session";

const MOCK_PLANTS = [
  {
    id: "p_1",
    name: "금스타티라",
    coverUrl:
      "https://images.unsplash.com/photo-1485955900006-10f4d324d411?auto=format&fit=crop&w=900&q=60",
    roomImageUrl:
      "https://images.unsplash.com/photo-1505691938895-1758d7feb511?auto=format&fit=crop&w=1200&q=60",
    "어린이.안전.등급": "주의",
    water_interval_days_spring: 6,
    water_interval_days_summer: 1,
    water_interval_days_fall: 7,
    water_interval_days_winter: 16,
    fertilize_interval_days_spring: 45,
    fertilize_interval_days_summer: 45,
    fertilize_interval_days_fall: 60,
    fertilize_interval_days_winter: 90,
    light_min_lux: 800,
    light_max_lux: 1500,
    window_distance_min_cm: 50,
    window_distance_max_cm: 150,
    direct_sun_risk_level: 1,
  },
  {
    id: "p_2",
    name: "스투키",
    coverUrl:
      "https://images.unsplash.com/photo-1483794344563-d27a8d18014e?auto=format&fit=crop&w=900&q=60",
    roomImageUrl:
      "https://images.unsplash.com/photo-1501045661006-fcebe0257c3f?auto=format&fit=crop&w=1200&q=60",
    "어린이.안전.등급": "주의",
    water_interval_days_spring: 10,
    water_interval_days_summer: 4,
    water_interval_days_fall: 12,
    water_interval_days_winter: 20,
    fertilize_interval_days_spring: 60,
    fertilize_interval_days_summer: 60,
    fertilize_interval_days_fall: 90,
    fertilize_interval_days_winter: 120,
    light_min_lux: 600,
    light_max_lux: 1400,
    window_distance_min_cm: 40,
    window_distance_max_cm: 120,
    direct_sun_risk_level: 1,
  },
  {
    id: "p_3",
    name: "테이블야자",
    coverUrl:
      "https://images.unsplash.com/photo-1501004318641-b39e6451bec6?auto=format&fit=crop&w=900&q=60",
    roomImageUrl:
      "https://images.unsplash.com/photo-1505693314120-0d443867891c?auto=format&fit=crop&w=1200&q=60",
    "어린이.안전.등급": "주의",
    water_interval_days_spring: 7,
    water_interval_days_summer: 3,
    water_interval_days_fall: 8,
    water_interval_days_winter: 14,
    fertilize_interval_days_spring: 45,
    fertilize_interval_days_summer: 45,
    fertilize_interval_days_fall: 60,
    fertilize_interval_days_winter: 90,
    light_min_lux: 500,
    light_max_lux: 1200,
    window_distance_min_cm: 60,
    window_distance_max_cm: 160,
    direct_sun_risk_level: 2,
  },
];

const MOCK_LOGS = [
  { id: "1", plantId: "p_1", plantName: "금스타티라", type: "water", date: "2026-02-03", time: "09:10", title: "물 줌", detail: "" },
  { id: "2", plantId: "p_1", plantName: "금스타티라", type: "move", date: "2026-02-03", time: "13:40", title: "위치 이동", detail: "거실 → 베란다" },
  { id: "3", plantId: "p_1", plantName: "금스타티라", type: "note", date: "2026-02-03", time: "20:05", title: "특이사항", detail: "잎 끝이 갈변했어요." },
  { id: "4", plantId: "p_2", plantName: "스투키", type: "fertilizer", date: "2026-02-01", time: "10:30", title: "비료 줌", detail: "" },
  {
    id: "5",
    plantId: "p_2",
    plantName: "스투키",
    type: "photo",
    date: "2026-02-01",
    time: "21:00",
    title: "배치 사진 저장",
    detail: "거실 배치 기록",
    imageUrl: "https://images.unsplash.com/photo-1505693314120-0d443867891c?auto=format&fit=crop&w=900&q=60",
  },
  { id: "6", plantId: "p_3", plantName: "테이블야자", type: "new", date: "2026-01-28", time: "15:10", title: "새 식물 추가", detail: "" },
];

export default function useTimeLogData({ useMockCreate = false, useMockData = false } = {}) {
  const [plants, setPlants] = useState(() => (useMockData ? MOCK_PLANTS : []));
  const [logs, setLogs] = useState(() => (useMockData ? MOCK_LOGS : []));
  const [loading, setLoading] = useState(false);

  const fetchPlants = useCallback(async () => {
    if (useMockData) {
      setPlants(MOCK_PLANTS);
      return;
    }
    try {
      const res = await fetchWithSession("/api/plantboard/plants");
      const data = await res.json();
      if (data.ok) {
        setPlants(data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch plants:", err);
    }
  }, [useMockData]);

  const fetchLogs = useCallback(async () => {
    if (useMockData) {
      setLogs(MOCK_LOGS);
      return;
    }
    try {
      setLoading(true);
      const res = await fetchWithSession("/api/plantboard/logs");
      const data = await res.json();
      if (data.ok) {
        setLogs(data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch logs:", err);
    } finally {
      setLoading(false);
    }
  }, [useMockData]);

  const createLog = useCallback(
    async (logData) => {
      if (useMockCreate) {
        const id =
          (typeof crypto !== "undefined" && crypto.randomUUID && crypto.randomUUID()) ||
          `mock-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
        const mockLog = { ...logData, id, _local: true };
        setLogs((prev) => [mockLog, ...prev]);
        return;
      }

      try {
        const res = await fetchWithSession("/api/plantboard/logs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ log: logData }),
        });
        const data = await res.json();
        if (data.ok) {
          fetchLogs();
        }
      } catch (err) {
        console.error("Failed to create log:", err);
      }
    },
    [fetchLogs, useMockCreate]
  );

  const createPlant = useCallback(
    async (plantData) => {
      try {
        const res = await fetchWithSession("/api/plantboard/plants", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plant: plantData }),
        });
        const data = await res.json();
        if (data.ok) {
          await fetchPlants();
          return data.item;
        }
      } catch (err) {
        console.error("Failed to create plant:", err);
      }
      return null;
    },
    [fetchPlants]
  );

  const deleteLog = useCallback(
    async (logId) => {
      if (useMockCreate && String(logId).startsWith("mock-")) {
        setLogs((prev) => prev.filter((log) => log.id !== logId));
        return;
      }
      try {
        const res = await fetchWithSession(`/api/plantboard/logs/${logId}`, {
          method: "DELETE",
        });
        const data = await res.json();
        if (data.ok) {
          fetchLogs();
        }
      } catch (err) {
        console.error("Failed to delete log:", err);
      }
    },
    [fetchLogs, useMockCreate]
  );

  useEffect(() => {
    fetchPlants();
    fetchLogs();
  }, [fetchPlants, fetchLogs]);

  return {
    plants,
    logs,
    loading,
    fetchPlants,
    fetchLogs,
    createLog,
    createPlant,
    deleteLog,
  };
}
