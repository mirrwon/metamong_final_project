import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchWithSession } from "../../services/session";
import { ROUTES } from "../../constants/routes";
import "./Survey.css";

const API_ORIGIN = "http://localhost:8000";
const PLANTS_API = `${API_ORIGIN}/api/plants`;

const SURVEY_STORAGE_KEY = "survey_answers";
const SELECTED_PLANT_KEY = "selected_plant";

const resolveImageUrl = (url) => {
  if (!url) return null;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (url.startsWith("/")) return `${API_ORIGIN}${url}`;
  return url;
};

const toArray = (val) => {
  if (Array.isArray(val)) return val;
  if (val == null) return [];
  return [val];
};

const normalizeValues = (val) =>
  toArray(val)
    .map((v) => String(v).trim().toLowerCase())
    .filter(Boolean);

const sizeTokenFromText = (text) => {
  const v = String(text || "").toLowerCase();
  if (!v) return null;
  if (v.includes("small") || v.includes("소") || v.includes("미니") || v.includes("s ")) return "small";
  if (v.includes("large") || v.includes("대") || v.includes("라지") || v.includes("l ")) return "large";
  if (v.includes("medium") || v.includes("중") || v.includes("m ")) return "medium";
  return null;
};

const styleTokensFromText = (text) => {
  const v = String(text || "").toLowerCase();
  if (!v) return [];
  const tokens = [];
  if (v.includes("natural") || v.includes("내추럴") || v.includes("자연") || v.includes("우드")) {
    tokens.push("natural");
  }
  if (v.includes("minimal") || v.includes("미니멀") || v.includes("모던") || v.includes("심플")) {
    tokens.push("minimal");
  }
  if (v.includes("trendy") || v.includes("트렌디") || v.includes("컬러") || v.includes("화려") || v.includes("강렬")) {
    tokens.push("trendy");
  }
  return tokens;
};

const plantStyleTokensFromText = (text) => {
  const v = String(text || "").toLowerCase();
  if (!v) return [];
  const tokens = [];
  if (v.includes("flowery") || v.includes("flower") || v.includes("꽃") || v.includes("화려")) {
    tokens.push("flowery");
  }
  if (v.includes("leafy") || v.includes("leaf") || v.includes("잎") || v.includes("관엽")) {
    tokens.push("leafy");
  }
  if (v.includes("fruity") || v.includes("fruit") || v.includes("열매") || v.includes("과일")) {
    tokens.push("fruity");
  }
  return tokens;
};

const collectTokens = (values, mapper) => {
  const tokens = new Set();
  values.forEach((val) => {
    mapper(val).forEach((t) => tokens.add(t));
  });
  return Array.from(tokens);
};

const matchGroup = (wanted, tokens, allowMissing = false) => {
  const targets = normalizeValues(wanted);
  if (targets.length === 0) return true;
  if (!tokens || tokens.length === 0) return allowMissing;
  return targets.some((t) => tokens.includes(t));
};

const buildPlantFilters = (plant) => {
  const sizeTokens = collectTokens(toArray(plant?.size), (val) => {
    const token = sizeTokenFromText(val);
    return token ? [token] : [];
  });

  const styleSource = [
    plant?.style,
    plant?.tags,
    plant?.placement,
    plant?.name,
    plant?.name_ko,
    plant?.name_en,
    plant?.care,
  ];
  const styleTokens = collectTokens(styleSource.flatMap(toArray), styleTokensFromText);

  const plantStyleSource = [
    plant?.plant_style,
    plant?.plantStyle,
    plant?.type,
    plant?.name,
    plant?.name_ko,
    plant?.name_en,
  ];
  const plantStyleTokens = collectTokens(plantStyleSource.flatMap(toArray), plantStyleTokensFromText);

  return { sizeTokens, styleTokens, plantStyleTokens };
};

const filterPlantsBySurvey = (plants, answers) => {
  const cautionWanted = normalizeValues(answers?.caution);
  const sizeWanted = answers?.size || [];
  const styleWanted = answers?.style || [];
  const plantStyleWanted = answers?.Plant_style || answers?.plant_style || answers?.plantStyle || [];

  const hasPetCaution = cautionWanted.includes("dog") || cautionWanted.includes("cat");
  const hasAllergyCaution = cautionWanted.includes("allergy") || cautionWanted.includes("baby");
  const hasBeginnerCaution = cautionWanted.includes("beginner");

  const isAllergyRisk = (plant) => {
    const val = plant?.allergy;
    if (val == null) return false;
    const text = String(val).toLowerCase().trim();
    if (!text) return false;
    if (["none", "no", "0", "false", "없음", "무", "안전"].includes(text)) return false;
    return true;
  };

  const isHardCare = (plant) => {
    const val = plant?.care;
    if (val == null) return false;
    const text = String(val).toLowerCase();
    return (
      text.includes("hard") ||
      text.includes("difficult") ||
      text.includes("expert") ||
      text.includes("high") ||
      text.includes("어려") ||
      text.includes("난이도") ||
      text.includes("고난") ||
      text.includes("상")
    );
  };

  return plants.filter((plant) => {
    if (hasPetCaution && plant?.pet_safe !== true) return false;
    if (hasAllergyCaution && isAllergyRisk(plant)) return false;
    if (hasBeginnerCaution && isHardCare(plant)) return false;

    const { sizeTokens, styleTokens, plantStyleTokens } = buildPlantFilters(plant);
    const sizeOk = matchGroup(sizeWanted, sizeTokens, false);
    const styleOk = matchGroup(styleWanted, styleTokens, true);
    const plantStyleOk = matchGroup(plantStyleWanted, plantStyleTokens, true);
    return sizeOk && styleOk && plantStyleOk;
  });
};

const shuffle = (arr) => {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
};

const DISPLAY_COUNT = 8;

const fetchAllPlants = async () => {
  const items = [];
  let offset = 0;
  let safety = 0;

  while (offset !== null && safety < 200) {
    const response = await fetchWithSession(`${PLANTS_API}?limit=100&offset=${offset}`);
    if (!response.ok) throw new Error("plants_failed");
    const data = await response.json();
    const pageItems = Array.isArray(data?.items) ? data.items : [];
    items.push(...pageItems);
    offset = data?.next_offset ?? null;
    safety += 1;
  }

  return items;
};

export default function PlantSelectPage() {
  const nav = useNavigate();
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [error, setError] = useState("");
  const [survey, setSurvey] = useState(null);

  const [allPlants, setAllPlants] = useState([]);
  const [filteredPlants, setFilteredPlants] = useState([]);
  const [visiblePlants, setVisiblePlants] = useState([]);
  const [remainingPlants, setRemainingPlants] = useState([]);

  useEffect(() => {
    const raw = sessionStorage.getItem(SURVEY_STORAGE_KEY);
    if (!raw) {
      setError("설문 데이터를 찾지 못했습니다. 다시 설문을 진행해주세요.");
      setStatus("error");
      return;
    }
    try {
      const parsed = JSON.parse(raw);
      setSurvey(parsed);
    } catch (e) {
      setError("설문 데이터를 읽을 수 없습니다. 다시 설문을 진행해주세요.");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    if (!survey) return;
    let alive = true;

    const run = async () => {
      setStatus("loading");
      setError("");
      try {
        const plants = await fetchAllPlants();
        if (!alive) return;
        setAllPlants(plants);
        setStatus("ready");
      } catch (e) {
        if (!alive) return;
        setError("식물 데이터를 불러오지 못했습니다.");
        setStatus("error");
      }
    };

    run();
    return () => {
      alive = false;
    };
  }, [survey]);

  useEffect(() => {
    if (status !== "ready") return;
    const filtered = filterPlantsBySurvey(allPlants, survey || {});
    const normalized = filtered
      .map((plant) => {
        const image = resolveImageUrl(plant?.image) || resolveImageUrl(plant?.images?.[0]);
        return {
          ...plant,
          displayName: plant?.name || plant?.name_ko || plant?.name_en || "식물",
          displayImage: image,
        };
      })
      .filter((plant) => plant.displayImage);

    const shuffled = shuffle(normalized);
    setFilteredPlants(shuffled);
    setVisiblePlants(shuffled.slice(0, DISPLAY_COUNT));
    setRemainingPlants(shuffled.slice(DISPLAY_COUNT));
  }, [status, allPlants, survey]);

  const remainingCount = remainingPlants.length;

  const handleShowMore = () => {
    if (remainingPlants.length === 0) return;
    const shuffled = shuffle(remainingPlants);
    setVisiblePlants(shuffled.slice(0, DISPLAY_COUNT));
    setRemainingPlants(shuffled.slice(DISPLAY_COUNT));
  };

  const handlePick = (plant) => {
    const payload = {
      id: plant?.id ?? null,
      name: plant?.displayName ?? plant?.name ?? "식물",
      image: plant?.displayImage ?? null,
    };
    sessionStorage.setItem(SELECTED_PLANT_KEY, JSON.stringify(payload));
    nav(ROUTES.ANALYZE);
  };

  const summaryText = useMemo(() => {
    if (!survey) return "";
    const size = normalizeValues(survey.size).join(", ");
    const style = normalizeValues(survey.style).join(", ");
    const plantStyle = normalizeValues(survey.Plant_style || survey.plant_style || survey.plantStyle).join(", ");

    const parts = [];
    if (size) parts.push(`크기: ${size}`);
    if (style) parts.push(`스타일: ${style}`);
    if (plantStyle) parts.push(`식물 스타일: ${plantStyle}`);
    return parts.join(" / ");
  }, [survey]);

  return (
    <div className="surveyPage">
      <div className="surveyShell">
        <div className="surveyCard">
          <header className="surveyHeader">
            <h2 className="surveyTitle">식물 선택</h2>
            <p className="surveyDesc">설문 결과에 맞는 식물을 골라주세요.</p>
            {summaryText && <p className="surveyStatus">{summaryText}</p>}
          </header>

          {status === "loading" && <p className="surveyStatus">식물 목록을 불러오는 중...</p>}
          {status === "error" && <p className="surveyStatus surveyStatus--error">{error}</p>}

          {status === "ready" && filteredPlants.length === 0 && (
            <p className="surveyStatus surveyStatus--error">
              조건에 맞는 식물을 찾지 못했습니다. 설문 값을 확인해주세요.
            </p>
          )}

          {status === "ready" && visiblePlants.length > 0 && (
            <>
              <div className="plantSelectGrid">
                {visiblePlants.map((plant) => (
                  <div key={plant.id || plant.displayImage} className="plantCard">
                    <div className="plantCard__name">{plant.displayName}</div>
                    <div className="plantCard__imageWrap">
                      <img className="plantCard__img" src={plant.displayImage} alt={plant.displayName} />
                    </div>
                    <button className="chatBtn" type="button" onClick={() => handlePick(plant)}>
                      선택하고 분석하기
                    </button>
                  </div>
                ))}
              </div>

              <div className="plantSelectFooter">
                <button className="chatBtn" type="button" onClick={handleShowMore} disabled={remainingCount === 0}>
                  {remainingCount > 0 ? `다른 식물 보기 (${remainingCount}개 남음)` : "더 보여줄 식물이 없습니다"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
