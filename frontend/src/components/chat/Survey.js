import { useEffect, useMemo, useState } from "react";
import { fetchWithSession, readStoredUser } from "../../services/session";
import "./Survey.css";

const API_BASE = "http://localhost:8000/api/chat";
const SURVEY_API = `${API_BASE}/survey`;
const SURVEY_IMAGE_API = `${API_BASE}/survey/image`;
const API_ORIGIN = "http://localhost:8000";
const REQUIRE_UPLOAD_FIRST = true;

const resolveImageUrl = (url) => {
  if (!url) return null;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (url.startsWith("/")) return `${API_ORIGIN}${url}`;
  return url;
};

const normalizeOption = (option, index) => {
  if (option == null) {
    return {
      value: `option-${index + 1}`,
      label: `Option ${index + 1}`,
      image: null,
      children: [],
    };
  }

  if (typeof option === "string") {
    return {
      value: option,
      label: option,
      image: null,
      children: [],
    };
  }

  const value = option.value ?? option.key ?? option.id ?? option.label ?? `option-${index + 1}`;
  const label = option.label ?? option.text ?? option.value ?? option.key ?? `Option ${index + 1}`;
  const image =
    option.image ?? option.imageUrl ?? option.photo ?? option.img ?? option.thumbnail ?? null;
  const rawChildren = Array.isArray(option.children)
    ? option.children
    : Array.isArray(option.items)
    ? option.items
    : [];
  const children = rawChildren.map((child, idx) => normalizeOption(child, idx));

  return {
    value: String(value),
    label: String(label),
    image: image ? resolveImageUrl(String(image)) : null,
    children,
  };
};

const normalizeGroups = (payload) => {
  if (!payload) return [];

  const rawGroups = Array.isArray(payload.groups)
    ? payload.groups
    : Array.isArray(payload.items)
    ? payload.items
    : payload.options || payload.key || payload.label
    ? [payload]
    : [];

  return rawGroups
    .map((group, index) => {
      const options = Array.isArray(group.options)
        ? group.options.map((option, idx) => normalizeOption(option, idx))
        : [];

      return {
        key: group.key ?? group.id ?? `group-${index + 1}`,
        label: group.label ?? group.title ?? `Question ${index + 1}`,
        description: group.description ?? group.desc ?? "",
        ui: group.ui ?? group.view ?? group.render ?? null,
        multiple: Boolean(group.multiple) || (typeof group.max === "number" && group.max > 1),
        max: typeof group.max === "number" ? group.max : null,
        optional: Boolean(group.optional),
        options,
      };
    })
    .filter((group) => group.options.length > 0);
};

const normalizeSurvey = (data) => {
  if (!data) return null;
  const payload = data.survey || data.payload || data.data || data;
  const groups = normalizeGroups(payload);

  if (!groups.length) return null;

  return {
    key: payload.key ?? payload.id ?? "survey",
    title: payload.title ?? payload.label ?? data.title ?? "Survey",
    description: payload.description ?? data.description ?? "",
    groups,
  };
};

export default function JoinSurvey({ onComplete, allowSkip = true }) {
  const storedUser = readStoredUser();
  const username = storedUser?.user_name || storedUser?.username || "";
  const [survey, setSurvey] = useState(null);
  const [status, setStatus] = useState("idle");
  const [selected, setSelected] = useState({});
  const [activeChildren, setActiveChildren] = useState({});
  const [loadError, setLoadError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploadFiles, setUploadFiles] = useState([]);
  const [uploadPreviewUrl, setUploadPreviewUrl] = useState("");
  const [uploadStatus, setUploadStatus] = useState("idle");
  const [uploadComplete, setUploadComplete] = useState(!REQUIRE_UPLOAD_FIRST);

  const canSkip = allowSkip && typeof onComplete === "function" && uploadComplete;

  useEffect(() => {
    if (!uploadComplete) return;
    let active = true;

    const fetchSurvey = async () => {
      setStatus("loading");
      setLoadError("");

      try {
        const response = await fetchWithSession(SURVEY_API, { method: "GET" });
        if (!response.ok) throw new Error("failed");

        const data = await response.json();
        const normalized = normalizeSurvey(data);
        if (!normalized) throw new Error("invalid");

        if (!active) return;
        setSurvey(normalized);
        setStatus("ready");
      } catch (error) {
        if (!active) return;
        setLoadError("Failed to load survey.");
        setStatus("error");
      }
    };

    fetchSurvey();

    return () => {
      active = false;
    };
  }, [uploadComplete]);

  useEffect(() => {
    if (!survey?.groups) return;
    setSelected((prev) => {
      const next = {};
      survey.groups.forEach((group) => {
        next[group.key] = Array.isArray(prev[group.key]) ? prev[group.key] : [];
      });
      return next;
    });
  }, [survey]);

  useEffect(() => {
    return () => {
      if (uploadPreviewUrl) URL.revokeObjectURL(uploadPreviewUrl);
    };
  }, [uploadPreviewUrl]);

  const allAnswered = useMemo(() => {
    if (!survey?.groups?.length) return false;
    return survey.groups.every((group) => {
      if (group.optional) return true;
      return (selected[group.key] || []).length > 0;
    });
  }, [survey, selected]);

  const computeNextSelection = (current, value, isMultiple, max) => {
    const hasValue = current.includes(value);
    if (isMultiple) {
      if (hasValue) return current.filter((item) => item !== value);
      if (!max || current.length < max) return [...current, value];
      return current;
    }
    return hasValue ? [] : [value];
  };

  const handleOptionToggle = (groupKey, value, isMultiple, max) => {
    setSelected((prev) => {
      const current = Array.isArray(prev[groupKey]) ? prev[groupKey] : [];
      const next = computeNextSelection(current, value, isMultiple, max);
      return { ...prev, [groupKey]: next };
    });
  };

  const handleParentToggle = (groupKey, option, isMultiple, max, currentSelection) => {
    const next = computeNextSelection(currentSelection, option.value, isMultiple, max);
    setSelected((prev) => ({ ...prev, [groupKey]: next }));
    setActiveChildren((prev) => ({
      ...prev,
      [groupKey]: option.children?.length && next.includes(option.value) ? option.value : null,
    }));
  };

  const handleSubmit = async () => {
    if (!survey || !allAnswered || status === "submitting" || !uploadComplete) return;

    setStatus("submitting");
    setSubmitError("");

    try {
      const response = await fetchWithSession(SURVEY_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          survey_key: survey.key,
          answers: selected,
          username,
        }),
      });

      if (!response.ok) throw new Error("failed");

      const data = await response.json();
      setStatus("done");
      if (typeof onComplete === "function") onComplete(data);
    } catch (error) {
      setStatus("ready");
      setSubmitError("Failed to submit survey.");
    }
  };

  const handleSkip = () => {
    if (typeof onComplete === "function") onComplete(null);
  };

  const handleUploadChange = (event) => {
    const files = event.target.files ? Array.from(event.target.files) : [];
    if (uploadPreviewUrl) URL.revokeObjectURL(uploadPreviewUrl);
    setUploadFiles(files);
    setUploadPreviewUrl(files[0] ? URL.createObjectURL(files[0]) : "");
    setUploadError("");
  };

  const handleUploadSubmit = async (event) => {
    event.preventDefault();
    if (uploadFiles.length === 0 || uploadStatus === "uploading") return;

    setUploadStatus("uploading");
    setUploadError("");

    const formData = new FormData();
    uploadFiles.forEach((file) => formData.append("files", file));
    formData.append("survey_key", survey?.key || "survey");
    if (username) {
      formData.append("username", username);
    }

    try {
      const response = await fetchWithSession(SURVEY_IMAGE_API, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("failed");
      await response.json();
      setUploadStatus("done");
      setUploadFiles([]);
      if (uploadPreviewUrl) URL.revokeObjectURL(uploadPreviewUrl);
      setUploadPreviewUrl("");
      setUploadComplete(true);
    } catch (error) {
      setUploadStatus("idle");
      setUploadError("Failed to upload images.");
    }
  };

  return (
    <div className="surveyPage">
      <div className="surveyShell">
        <div className="surveyCard">
          {!uploadComplete ? (
            <div className="surveyGate">
              <header className="surveyHeader">
                <h2 className="surveyTitle">방 사진을 업로드 해주세요</h2>
                <p className="surveyDesc">최적의 스팟을 추천해 드릴게요</p>
              </header>
              <form className="surveyUpload surveyUpload--gate" onSubmit={handleUploadSubmit}>
                <label className="surveyUpload__pick">
                  <input
                    className="surveyUpload__input"
                    type="file"
                    accept="image/*"
                    multiple
                    onChange={handleUploadChange}
                  />
                  <span className="surveyUpload__text">
                    {uploadFiles.length
                      ? `선택된 이미지 ${uploadFiles.length}개`
                      : "이미지 업로드"}
                  </span>
                </label>
                <button
                  className="chatBtn"
                  type="submit"
                  disabled={uploadFiles.length === 0 || uploadStatus === "uploading"}
                >
                  {uploadStatus === "uploading" ? "업로드 중.." : "업로드"}
                </button>
              </form>
              {uploadPreviewUrl && (
                <div className="surveyUploadPreview">
                  <img
                    className="surveyUploadPreview__img"
                    src={uploadPreviewUrl}
                    alt="Selected preview"
                  />
                </div>
              )}
              {uploadError && <p className="surveyStatus surveyStatus--error">{uploadError}</p>}
            </div>
          ) : (
            <>
              <header className="surveyHeader">
                <h2 className="surveyTitle">{survey?.title || "Survey"}</h2>
                {survey?.description && <p className="surveyDesc">{survey.description}</p>}
                {status === "loading" && <p className="surveyStatus">Loading survey...</p>}
                {loadError && <p className="surveyStatus surveyStatus--error">{loadError}</p>}
              </header>

              {survey?.groups?.map((group) => {
                const isMultiple = group.multiple;
                const selectedValues = selected[group.key] || [];
                const useCheckboxes =
                  group.ui === "checkbox" ||
                  group.ui === "check" ||
                  group.ui === "list" ||
                  group.options.every((option) => !option.image);

                const renderCheckLabel = (option) => (
                  <span
                    className={`surveyCheck__label${
                      option.image ? " surveyCheck__label--image" : ""
                    }`}
                  >
                    {option.image && (
                      <img className="surveyCheck__thumb" src={option.image} alt={option.label} />
                    )}
                    <span className="surveyCheck__text">{option.label}</span>
                  </span>
                );

                const renderParentChecks = (options) => (
                  <div className="surveyChecks">
                    {options.map((option, index) => {
                      const isSelected = selectedValues.includes(option.value);
                      return (
                        <label key={`${group.key}-${option.value}-${index}`} className="surveyCheck">
                          <input
                            className="surveyCheck__input"
                            type="checkbox"
                            checked={isSelected}
                            onChange={() =>
                              handleParentToggle(
                                group.key,
                                option,
                                isMultiple,
                                group.max,
                                selectedValues
                              )
                            }
                          />
                          {renderCheckLabel(option)}
                        </label>
                      );
                    })}
                  </div>
                );

                const renderChildChecks = (options, depth = 0, path = "") => (
                  <div
                    className="surveyChecks surveyChecks--nested"
                    style={
                      depth > 0 ? { marginTop: "8px", paddingLeft: `${depth * 16}px` } : undefined
                    }
                  >
                    {options.map((option, index) => {
                      const isSelected = selectedValues.includes(option.value);
                      const optionKey = `${path}${option.value}-${index}`;

                      return (
                        <div key={optionKey} className="surveyChildItem">
                          <label className="surveyCheck">
                            <input
                              className="surveyCheck__input"
                              type="checkbox"
                              checked={isSelected}
                              onChange={() =>
                                handleOptionToggle(group.key, option.value, isMultiple, group.max)
                              }
                            />
                            {renderCheckLabel(option)}
                          </label>
                          {option.children?.length && isSelected
                            ? renderChildChecks(option.children, depth + 1, `${optionKey}-`)
                            : null}
                        </div>
                      );
                    })}
                  </div>
                );

                const activeChildPanels = group.options
                  .filter(
                    (option) =>
                      option.children?.length &&
                      selectedValues.includes(option.value) &&
                      activeChildren[group.key] === option.value
                  )
                  .map((option, index) => (
                    <div key={`${group.key}-childpanel-${index}`} className="surveyChildPanel">
                      {renderChildChecks(option.children, 0, `${group.key}-${option.value}-`)}
                    </div>
                  ));

                return (
                  <section key={group.key} className="surveyGroup">
                    <div className="surveyGroup__header">
                      <h3 className="surveyGroup__title">{group.label}</h3>
                      {group.description && (
                        <p className="surveyGroup__desc">{group.description}</p>
                      )}
                      {group.max ? (
                        <p className="surveyGroup__meta">Select up to {group.max}</p>
                      ) : null}
                    </div>

                    {useCheckboxes ? (
                      <>
                        {renderParentChecks(group.options)}
                        {activeChildPanels.length > 0 && (
                          <div className="surveyChildPanels">{activeChildPanels}</div>
                        )}
                      </>
                    ) : (
                      <>
                        <div className="surveyOptions">
                          {group.options.map((option) => {
                            const isSelected = selectedValues.includes(option.value);

                            return (
                              <button
                                key={`${group.key}-${option.value}`}
                                type="button"
                                className={`surveyOption${
                                  isSelected ? " surveyOption--selected" : ""
                                }`}
                                onClick={() =>
                                  handleParentToggle(
                                    group.key,
                                    option,
                                    isMultiple,
                                    group.max,
                                    selectedValues
                                  )
                                }
                                aria-pressed={isSelected}
                              >
                                <div className="surveyOption__imageWrap">
                                  {option.image ? (
                                    <img
                                      className="surveyOption__img"
                                      src={option.image}
                                      alt={option.label}
                                    />
                                  ) : (
                                    <div className="surveyOption__placeholder">No image</div>
                                  )}
                                </div>
                                <div className="surveyOption__label">{option.label}</div>
                              </button>
                            );
                          })}
                        </div>
                        {activeChildPanels.length > 0 && (
                          <div className="surveyChildPanels">{activeChildPanels}</div>
                        )}
                      </>
                    )}
                  </section>
                );
              })}

              <footer className="surveyFooter">
                <button
                  className="chatBtn"
                  type="button"
                  onClick={handleSubmit}
                  disabled={!allAnswered || status === "submitting"}
                >
                  {status === "submitting" ? "Submitting..." : "Submit"}
                </button>
                {canSkip && (
                  <button className="chatBtn" type="button" onClick={handleSkip}>
                    Skip
                  </button>
                )}
                {submitError && <p className="surveyStatus surveyStatus--error">{submitError}</p>}
              </footer>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
