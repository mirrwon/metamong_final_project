import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../common/Button";
import api from "../../services/api";

const API_BASE = "/api/diary";

const normalizeDiaryItems = (payload) => {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  return payload.items || payload.data || [];
};

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

const resolveImageUrl = (item) => {
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

const DiaryList = () => {
  const nav = useNavigate();
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [sortOrder, setSortOrder] = useState("desc"); // asc | desc
  const [search, setSearch] = useState("");

  useEffect(() => {
    const fetchDiary = async () => {
      setStatus("loading");

      // 1) axios(api 인스턴스)로 시도
      try {
        const response = await api.get(API_BASE);
        const list = normalizeDiaryItems(response.data);
        setItems(list);
        setStatus("ready");
        return;
      } catch (error) {
        // 2) 백 미연결/설정 문제 대비: fetch로 한 번 더 시도
        try {
          const res = await fetch(API_BASE);
          if (!res.ok) throw new Error("failed");
          const data = await res.json();
          const list = normalizeDiaryItems(data);
          setItems(list);
          setStatus("ready");
          return;
        } catch (e) {
          // 백이 없으면 여기로 오는 게 정상
          setStatus("error");
        }
      }
    };

    fetchDiary();
  }, []);

  const filteredItems = useMemo(() => {
    const trimmedSearch = search.trim().toLowerCase();

    return items
      .filter((item) => {
        if (!trimmedSearch) return true;
        const title = (item?.title || "").toLowerCase();
        const content = (item?.content || item?.body || "").toLowerCase();
        return title.includes(trimmedSearch) || content.includes(trimmedSearch);
      })
      .sort((a, b) => {
        const first = new Date(getItemDateValue(a) || 0).getTime();
        const second = new Date(getItemDateValue(b) || 0).getTime();
        return sortOrder === "asc" ? first - second : second - first;
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
    <div className="">
      <div className="">
        <h1 className="">My Plant Diary</h1>
        <div className="" />
      </div>

      <div className="">
        <button type="button" className="" onClick={handleSortToggle}>
          날짜 정렬 ({sortOrder === "asc" ? "오래된순" : "최신순"})
        </button>

        <input
          className=""
          type="search"
          placeholder="검색"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />

        <Button
          text="New Post"
          type="primary"
          className=""
          onClick={() => nav("/diary/new")}
        />
      </div>

      <div className="">
        {status === "loading" && (
          <div className="">Loading diary entries...</div>
        )}

        {status === "error" && (
          <div className="">
            Failed to load diary data. (백엔드 미연결이면 정상)
          </div>
        )}

        {status === "ready" && filteredItems.length === 0 && (
          <div className="">No diary entries found.</div>
        )}

        {filteredItems.length > 0 && (
          <div className="">
            {filteredItems.map((item, index) => {
              const imageUrl = resolveImageUrl(item);
              const dateLabel = formatDateLabel(getItemDateValue(item));
              const title = item?.title || "제목 없음";
              const content = item?.content || item?.body || "";
              const itemId = item?.id || item?._id || "";
              const key = itemId || `${title}-${index}`;

              return (
                <article
                  key={key}
                  className=""
                  onClick={() => handleOpenPost(itemId)}
                >
                  <div className="">
                    {imageUrl ? (
                      <img src={imageUrl} alt={title} />
                    ) : (
                      <div className="">No photo available</div>
                    )}
                  </div>

                  <div className="">
                    <div className="">{dateLabel || "No date"}</div>
                    <h3 className="">{title}</h3>
                    <p className="">{content || "No content provided."}</p>
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

export default DiaryList;
