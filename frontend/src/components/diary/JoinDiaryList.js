import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../common/Button";
import api from "../../services/api";
import "./JoinDiaryList.css";
import { getStoredUsername } from "../../services/user";
import { fetchWithSession } from "../../services/session";

const API_BASE = "/api/diary";
const BACKEND_ORIGIN = "http://localhost:8000";

/* 응답 형태 통일 */
const normalizeDiaryItems = (payload) => {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  return payload.items || payload.data || [];
};

/* 날짜 필드 통합 */
const getItemDateValue = (item) => {
  return (
    item?.date ||
    item?.created_at ||
    item?.createdAt ||
    item?.createdDate ||
    item?.created_date ||
    null
  );
};

/* 이미지 URL 해결 (조원 수정 반영) */
const resolveImageUrl = (item) => {
  const filename = item?.image_filename || item?.imageFilename;
  if (filename) return `${BACKEND_ORIGIN}/uploads/${filename}`;

  return (
    item?.imageUrl ||
    item?.image_url ||
    item?.photoUrl ||
    item?.photo_url ||
    item?.photo ||
    item?.image ||
    ""
  );
};

const formatDateLabel = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-CA"); // YYYY-MM-DD
};

const JoinDiaryList = () => {
  const nav = useNavigate();
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [sortOrder, setSortOrder] = useState("desc"); // asc | desc
  const [search, setSearch] = useState("");

  useEffect(() => {
    const fetchDiary = async () => {
      setStatus("loading");
      const username = getStoredUsername();
      const queryString = username
        ? `?username=${encodeURIComponent(username)}`
        : "";

      try {
        const response = await api.get(API_BASE, {
          params: username ? { username } : undefined,
        });
        const list = normalizeDiaryItems(response.data);
        setItems(list);
        setStatus("ready");
        return;
      } catch (error) {
        try {
          const res = await fetchWithSession(`${API_BASE}${queryString}`);
          if (!res.ok) throw new Error("failed");
          const data = await res.json();
          const list = normalizeDiaryItems(data);
          setItems(list);
          setStatus("ready");
          return;
        } catch (e) {
          setStatus("error");
        }
      }
    };

    fetchDiary();
  }, []);

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();

    return items
      .filter((item) => {
        if (!keyword) return true;
        const title = (item?.title || "").toLowerCase();
        const content = (item?.content || item?.body || "").toLowerCase();
        return title.includes(keyword) || content.includes(keyword);
      })
      .sort((a, b) => {
        const aDate = new Date(getItemDateValue(a) || 0).getTime();
        const bDate = new Date(getItemDateValue(b) || 0).getTime();
        return sortOrder === "asc" ? aDate - bDate : bDate - aDate;
      });
  }, [items, search, sortOrder]);

  const handleSortToggle = () => {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
  };

  const handleOpenPost = (itemId) => {
    if (!itemId) return;
    nav(`/diary/${itemId}`);
  };

  return (
    <div className="diary-list">
      <div className="diary-list__head">
        <h1 className="diary-list__title">My Plant Diary</h1>
        <div className="ui-line diary-list__line" />
      </div>

      <div className="diary-list__controls">
        <Button
          text="날짜 정렬"
          type="option"
          className="ui-btn--compact diary-list__sort"
          onClick={handleSortToggle}
        />

        <input
          className="ui-input diary-list__search"
          type="search"
          placeholder="검색"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <Button
          text="New Post"
          type="primary"
          className="ui-btn--compact diary-list__new"
          onClick={() => nav("/diary/new")}
        />
      </div>

      <div className="diary-list__body">
        {status === "loading" && (
          <div className="diary-list__state">
            Loading diary entries...
          </div>
        )}

        {status === "error" && (
          <div className="diary-list__state">
            Failed to load diary data.
          </div>
        )}

        {status === "ready" && filteredItems.length === 0 && (
          <div className="diary-list__state">
            No diary entries found.
          </div>
        )}

        {filteredItems.length > 0 && (
          <div className="diary-list__items">
            {filteredItems.map((item, index) => {
              const imageUrl = resolveImageUrl(item);
              const cacheBustedImageUrl = imageUrl
                ? `${imageUrl}?t=${Date.now()}`
                : "";
              const dateLabel = formatDateLabel(getItemDateValue(item));
              const title = item?.title || "제목 없음";
              const content = item?.content || item?.body || "";
              const itemId = item?.id || item?._id || "";
              const key = itemId || `${title}-${index}`;

              return (
                <article
                  key={key}
                  className="diary-card"
                  onClick={() => handleOpenPost(itemId)}
                >
                  <div className="diary-card__thumb">
                    {imageUrl ? (
                      <img
                        className="diary-card__img"
                        src={cacheBustedImageUrl}
                        alt={title}
                      />
                    ) : (
                      <div className="diary-card__empty">
                        No photo
                      </div>
                    )}
                  </div>

                  <div className="diary-card__meta">
                    <div className="diary-card__date">
                      {dateLabel || "No date"}
                    </div>
                    <h3 className="diary-card__title">{title}</h3>
                    <p className="diary-card__excerpt">
                      {content || "No content provided."}
                    </p>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default JoinDiaryList;
