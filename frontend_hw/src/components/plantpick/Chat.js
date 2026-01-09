import { useEffect, useMemo, useRef, useState } from "react";
import Button from "../common/Button";
import "./Chat.css";

const API_BASE = "/api/chat";
const IMAGE_API = `${API_BASE}/image`;

const normalizeMessages = (payload) => {
  if (!payload) return [];
  const raw = Array.isArray(payload)
    ? payload
    : payload.messages || payload.data || [];

  return raw
    .filter((item) => item && item.text)
    .map((item, index) => ({
      id: item.id || `${Date.now()}-${index}`,
      role: item.role || "bot",
      text: item.text,
      timestamp: item.timestamp || null,
    }));
};

const normalizePayload = (data) => {
  if (!data) return null;
  const raw = data.payload || data.data?.payload || (data.photos ? data : null);
  if (!raw) return null;

  const resolvedInput =
    raw.input ||
    (raw.input_type
      ? {
          type: raw.input_type,
        }
      : null);
  const photos = Array.isArray(raw.photos) ? raw.photos : [];
  const attributeSchema = Array.isArray(raw.attributeSchema)
    ? raw.attributeSchema
    : photos[0]?.attributes
    ? Object.keys(photos[0].attributes).map((key) => ({
        key,
        label: key,
      }))
    : [];

  return {
    photos,
    attributeSchema,
    type: raw.type || "",
    groups: Array.isArray(raw.groups) ? raw.groups : [],
    question: raw.question || "",
    options: Array.isArray(raw.options) ? raw.options : [],
    input: resolvedInput,
  };
};

const formatTime = (timestamp) => {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
};

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState("idle");
  const [input, setInput] = useState("");
  const [imageFiles, setImageFiles] = useState([]);
  const [startHour, setStartHour] = useState("");
  const [endHour, setEndHour] = useState("");
  const [detailMode, setDetailMode] = useState(false);
  const [filterGroups, setFilterGroups] = useState([]);
  const [selectedFilters, setSelectedFilters] = useState({});
  const [filtersSent, setFiltersSent] = useState(false);
  const listRef = useRef(null);
  const endRef = useRef(null);
  const [lightboxImages, setLightboxImages] = useState([]);
  const [lightboxIndex, setLightboxIndex] = useState(0);

  const buildFilterSummary = () => {
    const groups =
      activeFilterGroups.length > 0 ? activeFilterGroups : filterGroups;
    const parts = groups
      .map((group) => {
        const values = selectedFilters[group.key] || [];
        if (values.length === 0) return null;
        return `${group.label}: ${values.join(", ")}`;
      })
      .filter(Boolean);
    if (parts.length === 0) return "선택한 속성 없음";
    return parts.join(" / ");
  };

  const sendWithFilters = async () => {
    setFiltersSent(false);
    const summaryText = buildFilterSummary();
    setMessages((prev) => [
      ...prev,
      {
        id: `${Date.now()}-user-filter`,
        role: "user",
        text: summaryText,
        timestamp: Date.now(),
      },
    ]);

    setStatus("loading");
    try {
      const response = await fetch(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: summaryText,
          filters: {
            ...selectedFilters,
          },
        }),
      });

      if (!response.ok) throw new Error("failed");

      const data = await response.json();
      const incoming = normalizeMessages(data);
      const nextPayload = normalizePayload(data);

      if (incoming.length) {
        setMessages((prev) => [...prev, ...incoming]);
      }

      if (nextPayload) {
        setPayload(nextPayload);
      }

      setStatus("connected");
      setFiltersSent(true);
    } catch (e) {
      setStatus("error");
      setFiltersSent(false);
    }
  };

  const handleOptionSelect = async (option) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `${Date.now()}-user`,
        role: "user",
        text: option,
        timestamp: Date.now(),
      },
    ]);

    setStatus("loading");
    try {
      const response = await fetch(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: option,
          filters: {
            ...selectedFilters,
          },
        }),
      });

      if (!response.ok) throw new Error("failed");

      const data = await response.json();
      const incoming = normalizeMessages(data);
      const nextPayload = normalizePayload(data);

      if (incoming.length) {
        setMessages((prev) => [...prev, ...incoming]);
      }

      if (nextPayload) {
        setPayload(nextPayload);
      }

      setStatus("connected");
    } catch (e) {
      setStatus("error");
    }
  };

  const hasMessages = messages.length > 0;
  const statusText = useMemo(() => {
    if (status === "loading") return "서버 응답 대기중";
    if (status === "connected") return "실시간 연결됨";
    if (status === "error") return "연결 실패";
    return "대기중";
  }, [status]);

  const attributeGridTemplate = useMemo(() => {
    const count = payload?.attributeSchema?.length || 0;
    if (!count) return null;
    return {
      gridTemplateColumns: `minmax(0, 1.2fr) repeat(${count}, minmax(0, 1fr))`,
    };
  }, [payload]);

  const shouldRenderInlineDetailInput = false;
  const textInputPlaceholder =
    payload?.input?.placeholder || (detailMode ? "상세 내용을 입력해주세요" : "");
  const activeFilterGroups =
    payload?.type === "filters" && Array.isArray(payload?.groups)
      ? payload.groups
      : filterGroups;
  const isPlantSelect =
    payload?.type === "filters" &&
    Array.isArray(payload?.groups) &&
    payload.groups.some((group) => group.key === "plants");

  useEffect(() => {
    if (!payload?.photos?.length) return;
    setMessages((prev) => {
      if (prev.some((message) => message.id === "payload-block")) {
        return prev;
      }
      return [
        ...prev,
        {
          id: "payload-block",
          role: "bot",
          type: "payload",
        },
      ];
    });
  }, [payload]);

  useEffect(() => {
    if (payload?.type !== "filters" || !Array.isArray(payload?.groups)) {
      return;
    }
    const groupKeys = payload.groups.map((group) => group.key);
    setSelectedFilters((prev) => {
      const next = {};
      groupKeys.forEach((key) => {
        next[key] = prev[key] || [];
      });
      return next;
    });
    setFiltersSent(false);
  }, [payload?.type, payload?.groups]);
  useEffect(() => {
    if (payload?.type === "filters") {
      setFiltersSent(false);
    }
  }, [payload?.type, payload?.groups, isPlantSelect]);

  useEffect(() => {
    const fetchMessages = async () => {
      setStatus("loading");
      try {
        const response = await fetch(API_BASE, { method: "GET" });
        if (!response.ok) throw new Error("failed");
        const data = await response.json();
        const nextMessages = normalizeMessages(data);
        const nextPayload = normalizePayload(data);
        setMessages(nextMessages);
        if (nextPayload) setPayload(nextPayload);
        setStatus("connected");
      } catch (error) {
        setStatus("error");
      }
    };

    fetchMessages();
  }, []);

  useEffect(() => {
    const fetchFilters = async () => {
      try {
        const response = await fetch(`${API_BASE}/filters`);
        if (!response.ok) throw new Error("failed");
        const data = await response.json();
        if (Array.isArray(data?.groups)) {
          setFilterGroups(data.groups);
          setSelectedFilters(
            data.groups.reduce((acc, group) => {
              acc[group.key] = [];
              return acc;
            }, {})
          );
        }
      } catch (error) {
        // keep defaults
      }
    };

    fetchFilters();
  }, []);

  useEffect(() => {
    if (!listRef.current) return;
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (!endRef.current) return;
    endRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, payload, detailMode]);

  const openLightbox = (images, index) => {
    if (!images.length) return;
    setLightboxImages(images);
    setLightboxIndex(index);
  };

  const closeLightbox = () => {
    setLightboxImages([]);
    setLightboxIndex(0);
  };

  const showPrev = (event) => {
    event.stopPropagation();
    setLightboxIndex((prev) =>
      prev === 0 ? lightboxImages.length - 1 : prev - 1
    );
  };

  const showNext = (event) => {
    event.stopPropagation();
    setLightboxIndex((prev) =>
      prev === lightboxImages.length - 1 ? 0 : prev + 1
    );
  };

  const handleDownload = () => {
    const item = lightboxImages[lightboxIndex];
    if (!item?.url) return;
    const link = document.createElement("a");
    link.href = item.url;
    link.download = item.name || "image";
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/stream`);
    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const incoming = normalizeMessages(data);
        const nextPayload = normalizePayload(data);
        if (incoming.length) {
          setMessages((prev) => [...prev, ...incoming]);
        }
        if (nextPayload) setPayload(nextPayload);
        setStatus("connected");
      } catch (error) {
        setStatus("error");
      }
    };
    source.onerror = () => {
      setStatus("error");
      source.close();
    };
    return () => source.close();
  }, []);

  const handleRefresh = async () => {
    setStatus("loading");
    try {
      const response = await fetch(API_BASE, { method: "GET" });
      if (!response.ok) throw new Error("failed");
      const data = await response.json();
      const nextMessages = normalizeMessages(data);
      const nextPayload = normalizePayload(data);
      setMessages(nextMessages);
      if (nextPayload) setPayload(nextPayload);
      setStatus("connected");
    } catch (error) {
      setStatus("error");
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;

    setMessages((prev) => [
      ...prev,
      {
        id: `${Date.now()}-user-input`,
        role: "user",
        text: trimmed,
        timestamp: Date.now(),
      },
    ]);

    setStatus("loading");
    try {
      const response = await fetch(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: trimmed,
          filters: {
            ...selectedFilters,
          },
        }),
      });
      if (!response.ok) throw new Error("failed");
      const data = await response.json();
      const incoming = normalizeMessages(data);
      const nextPayload = normalizePayload(data);
      if (incoming.length) {
        setMessages((prev) => [...prev, ...incoming]);
      }
      if (nextPayload) setPayload(nextPayload);
      setInput("");
      setStatus("connected");
    } catch (error) {
      setStatus("error");
    }
  };

  const handleImageChange = (event) => {
    const files = event.target.files ? Array.from(event.target.files) : [];
    setImageFiles(files);
  };

  const handleImageSubmit = async (event) => {
    event.preventDefault();
    if (imageFiles.length === 0) return;
    const label = `이미지 업로드 ${imageFiles.length}장`;

    setMessages((prev) => [
      ...prev,
      {
        id: `${Date.now()}-user-images`,
        role: "user",
        type: "images",
        images: imageFiles.map((file) => ({
          name: file.name,
          url: URL.createObjectURL(file),
        })),
        text: label,
        timestamp: Date.now(),
      },
    ]);

    const formData = new FormData();
    imageFiles.forEach((file) => {
      formData.append("files", file);
    });
    formData.append("text", label);

    setStatus("loading");
    try {
      const response = await fetch(IMAGE_API, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("failed");
      const data = await response.json();
      const incoming = normalizeMessages(data);
      const nextPayload = normalizePayload(data);
      if (incoming.length) {
        setMessages((prev) => [...prev, ...incoming]);
      }
      if (nextPayload) setPayload(nextPayload);
      setImageFiles([]);
      setStatus("connected");
    } catch (error) {
      setStatus("error");
    }
  };

  const handleTimeSubmit = async (event) => {
    event.preventDefault();
    if (startHour === "" || endHour === "") return;
    const label = `${startHour}시 ~ ${endHour}시`;

    setMessages((prev) => [
      ...prev,
      {
        id: `${Date.now()}-user-time`,
        role: "user",
        text: label,
        timestamp: Date.now(),
      },
    ]);

    setStatus("loading");
    try {
      const response = await fetch(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: label,
          filters: {
            ...selectedFilters,
          },
        }),
      });
      if (!response.ok) throw new Error("failed");
      const data = await response.json();
      const incoming = normalizeMessages(data);
      const nextPayload = normalizePayload(data);
      if (incoming.length) {
        setMessages((prev) => [...prev, ...incoming]);
      }
      if (nextPayload) setPayload(nextPayload);
      setStartHour("");
      setEndHour("");
      setStatus("connected");
    } catch (error) {
      setStatus("error");
    }
  };

  const handleDetailChoice = (choice) => {
    if (choice === "detail") {
      setDetailMode(true);
      setMessages((prev) => [
        ...prev,
         {
            id: `${Date.now()}-user-detail`,
            role: "user",
            text: "상세 입력할게요",
            timestamp: Date.now(),
        },
      ]);
      return;
    }
    setDetailMode(false);
    sendChoiceMessage("마음에 들어요");
  };

  const sendChoiceMessage = async (text) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `${Date.now()}-user-choice`,
        role: "user",
        text,
        timestamp: Date.now(),
      },
    ]);

    setStatus("loading");
    try {
      const response = await fetch(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          filters: {
            ...selectedFilters,
          },
        }),
      });
      if (!response.ok) throw new Error("failed");
      const data = await response.json();
      const incoming = normalizeMessages(data);
      const nextPayload = normalizePayload(data);
      if (incoming.length) {
        setMessages((prev) => [...prev, ...incoming]);
      }
      if (nextPayload) setPayload(nextPayload);
      setStatus("connected");
    } catch (error) {
      setStatus("error");
    }
  };

  const toggleFilterOption = (groupKey, value) => {
    setFiltersSent(false);
    setSelectedFilters((prev) => {
      const current = prev[groupKey] || [];
      const next = current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value];
      return { ...prev, [groupKey]: next };
    });
  };


  return (
    <div className="">
      <div className="">
        <div className="">
          <div>
            <h2 className="">추천 AI</h2>
            <p className="">
              고객님의 취향에 맞는 식물을 추천해드립니다.
            </p>
          </div>
          <div className="">
            <span className="" />
            {statusText}
          </div>
        </div>
        <div className="" ref={listRef}>
          {!hasMessages && (
            <div className="">아직 수신된 메시지가 없습니다.</div>
          )}
          {messages.map((message) => (
            <div
              key={message.id}
              className=""
            >
              {message.type === "payload" && payload?.photos?.length ? (
                <div className="">
                  <div className="">사진과 속성</div>
                  <div className="">
                    {payload.photos.map((photo, index) => (
                      <div key={photo.id || index} className="">
                        <div className="">
                          {photo.label || `사진 ${index + 1}`}
                        </div>
                        {photo.url || photo.imageUrl ? (
                          <img
                            className=""
                            src={photo.url || photo.imageUrl}
                            alt={photo.label || `사진 ${index + 1}`}
                            onClick={() =>
                              openLightbox(
                                payload.photos.map((item, idx) => ({
                                  name: item.label || `사진 ${idx + 1}`,
                                  url: item.url || item.imageUrl,
                                })),
                                index
                              )
                            }
                          />
                        ) : (
                          <div className="">이미지 없음</div>
                        )}
                      </div>
                    ))}
                  </div>

                  {payload.attributeSchema.length > 0 && (
                    <div className="">
                      <div
                        className=""
                        style={attributeGridTemplate || undefined}
                      >
                        <span>사진</span>
                        {payload.attributeSchema.map((schema) => (
                          <span key={schema.key}>{schema.label}</span>
                        ))}
                      </div>
                      {payload.photos.map((photo, index) => (
                        <div
                          key={photo.id || index}
                          className=""
                          style={attributeGridTemplate || undefined}
                        >
                          <span className="">
                            {photo.label || `사진 ${index + 1}`}
                          </span>
                          {payload.attributeSchema.map((schema) => (
                            <span
                              key={schema.key}
                              className=""
                            >
                              {photo.attributes?.[schema.key] || "-"}
                            </span>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="">
                    <div className="">
                      마음에 들지 않으면 상세 입력으로 이어갈까요?
                    </div>
                    <div className="">
                      <Button
                        type="option"
                        className=""
                        onClick={() => handleDetailChoice("ok")}
                        text="마음에 들어요"
                      />
                      <Button
                        type="primary"
                        className=""
                        onClick={() => handleDetailChoice("detail")}
                        text="상세 입력"
                      />
                    </div>
                  </div>
                </div>
              ) : message.type === "images" ? (
                <div className="">
                  <div className="">
                    {message.images?.map((image) => (
                      <div key={image.url} className="">
                        <div className="">{image.name}</div>
                        <img
                          className=""
                          src={image.url}
                          alt={image.name}
                          onClick={() =>
                            openLightbox(
                              message.images.map((item) => ({
                                name: item.name,
                                url: item.url,
                              })),
                              message.images.findIndex(
                                (item) => item.url === image.url
                              )
                            )
                          }
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  <div className="">{message.text}</div>
                  {message.timestamp && (
                    <div className="">
                      {formatTime(message.timestamp)}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}

          {payload?.options?.length > 0 && (
            <div className="">
              <div className="">
                {payload.options.map((option) => (
                  <Button
                    key={option}
                    type="option"
                    className=""
                    onClick={() => handleOptionSelect(option)}
                    text={option}
                  />
                ))}
              </div>
            </div>
          )}

          {payload?.type === "filters" &&
            activeFilterGroups.map((group) => (
              <div key={group.key}>
                <div>[{group.label}]</div>
                {group.options.map((option) => (
                  <label key={`${group.key}-${option}`}>
                  <input
                    type="checkbox"
                    checked={(selectedFilters[group.key] || []).includes(
                      option
                    )}
                    disabled={filtersSent}
                    onChange={() => toggleFilterOption(group.key, option)}
                  />
                    {option}
                  </label>
                ))}
              </div>
            ))}
          {payload?.type === "filters" && !filtersSent && (
          <div>
            <button type="button" onClick={sendWithFilters}>
              전송
            </button>
          </div>
        )}

          {(payload?.input?.type === "text" || detailMode) &&
            !shouldRenderInlineDetailInput && (
            <form className="" onSubmit={handleSubmit}>
              <input
                className=""
                type="text"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={textInputPlaceholder}
              />
              <button className="" type="submit">
                전송
              </button>
            </form>
          )}

          {payload?.input?.type === "time_range" && (
            <form className="" onSubmit={handleTimeSubmit}>
              <div className="">
                <label className="">
                  시작
                  <select
                    className=""
                    value={startHour}
                    onChange={(event) => setStartHour(event.target.value)}
                  >
                    <option value="">선택</option>
                    {Array.from({ length: 24 }, (_, i) => i).map((hour) => (
                      <option key={hour} value={hour}>
                        {hour}시
                      </option>
                    ))}
                  </select>
                </label>
                <span className="">~</span>
                <label className="">
                  종료
                  <select
                    className=""
                    value={endHour}
                    onChange={(event) => setEndHour(event.target.value)}
                  >
                    <option value="">선택</option>
                    {Array.from({ length: 24 }, (_, i) => i).map((hour) => (
                      <option key={hour} value={hour}>
                        {hour}시
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button className="" type="submit">
                전송
              </button>
            </form>
          )}

          {payload?.input?.type === "image" && (
            <form className="" onSubmit={handleImageSubmit}>
              <label className="">
                <input
                  className=""
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={handleImageChange}
                />
                <span className="">
                  {imageFiles.length
                    ? `선택된 이미지 ${imageFiles.length}장`
                    : "공간 사진을 업로드해주세요"}
                </span>
              </label>
              <button className="" type="submit">
                전송
              </button>
            </form>
          )}
          <div ref={endRef} />
        </div>

        {lightboxImages.length > 0 && (
          <div className="" onClick={closeLightbox}>
            <button
              className=""
              type="button"
              onClick={closeLightbox}
            >
              닫기
            </button>
            <button
              className=""
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                handleDownload();
              }}
            >
              이미지 다운로드
            </button>
            {lightboxImages.length > 1 && (
              <>
                <button
                  className=""
                  type="button"
                  onClick={showPrev}
                >
                  이전
                </button>
                <button
                  className=""
                  type="button"
                  onClick={showNext}
                >
                  다음
                </button>
              </>
            )}
            <div
              className=""
              onClick={(event) => event.stopPropagation()}
            >
              <img
                className=""
                src={lightboxImages[lightboxIndex]?.url}
                alt={lightboxImages[lightboxIndex]?.name || "확대 이미지"}
              />
              {lightboxImages[lightboxIndex]?.name && (
                <div className="">
                  {lightboxImages[lightboxIndex].name}
                </div>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
