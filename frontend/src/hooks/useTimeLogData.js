import { useCallback, useEffect, useState } from "react";

export default function useTimeLogData(username) {
  const [plants, setPlants] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchPlants = useCallback(async () => {
    try {
      const res = await fetch(`/api/plantboard/plants?username=${username}`);
      const data = await res.json();
      if (data.ok) {
        setPlants(data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch plants:", err);
    }
  }, [username]);

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`/api/plantboard/logs?username=${username}`);
      const data = await res.json();
      if (data.ok) {
        setLogs(data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch logs:", err);
    } finally {
      setLoading(false);
    }
  }, [username]);

  const createLog = useCallback(
    async (logData) => {
      try {
        const res = await fetch("/api/plantboard/logs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, log: logData }),
        });
        const data = await res.json();
        if (data.ok) {
          fetchLogs();
        }
      } catch (err) {
        console.error("Failed to create log:", err);
      }
    },
    [username, fetchLogs]
  );

  const createPlant = useCallback(
    async (plantData) => {
      try {
        const res = await fetch("/api/plantboard/plants", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, plant: plantData }),
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
    [username, fetchPlants]
  );

  const deleteLog = useCallback(
    async (logId) => {
      try {
        const res = await fetch(`/api/plantboard/logs/${logId}?username=${username}`, {
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
    [username, fetchLogs]
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
