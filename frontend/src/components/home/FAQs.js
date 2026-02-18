import { useState } from "react";
import "../../pages/Home.css";

const FAQ_list = [
  {
    id: 1,
    q: "식물 추천은 어떤 기준으로 되나요?",
    a: "AI가 공간 환경과 취향 정보를 바탕으로 추천해요.",
  },
  {
    id: 2,
    q: "추천 결과를 바로 구매할 수 있나요?",
    a: "식물 정보와 관리 팁을 제공하고, 구매는 별도 링크로 안내돼요.",
  },
  {
    id: 3,
    q: "사진 없이도 추천을 받을 수 있나요?",
    a: "네. 기본 질문만으로도 추천이 가능해요.",
  },
];

const FAQ_more = [
  {
    id: 4,
    q: "초보자에게 쉬운 식물도 추천해주나요?",
    a: "물 주기와 관리 난이도를 기준으로 쉬운 식물을 먼저 보여줘요.",
  },
  {
    id: 5,
    q: "반려동물이 있어도 안전한 식물을 알려주나요?",
    a: "반려동물 안전 정보를 포함해 필터링할 수 있어요.",
  },
  {
    id: 6,
    q: "추천 결과가 마음에 들지 않으면 다시 받을 수 있나요?",
    a: "네. 조건을 바꿔서 여러 번 추천을 받을 수 있어요.",
  },
];

const FAQs = () => {
  const [open, setOpen] = useState(false);

  return (
    <section className="faq">
      <div className="catalog-header catalog-header--faq">
        <div className="catalog-header__left">
          <h2 className="catalog-title faq__title">FAQ</h2>
        </div>
        <button
          className="catalog-more"
          type="button"
          onClick={() => setOpen(true)}
        >
          MORE
        </button>
      </div>
      <div className="catalog-divider" />

      <ol className="faq__list">
        {FAQ_list.map((item, idx) => (
          <li key={item.id} className="faq__item">
            <span className="faq__number">Q{idx + 1}.</span>
            <p className="faq__question">{item.q}</p>
            <p className="faq__answer">{item.a}</p>
          </li>
        ))}
      </ol>

      {open && (
        <div className="faq-modal" role="dialog" aria-modal="true">
          <button
            className="faq-modal__backdrop"
            type="button"
            onClick={() => setOpen(false)}
            aria-label="닫기"
          />
          <div className="faq-modal__panel">
            <div className="faq-modal__header">
              <h3 className="faq-modal__title">자주 묻는 질문</h3>
              <button
                className="faq-modal__close"
                type="button"
                onClick={() => setOpen(false)}
              >
                닫기
              </button>
            </div>
            <ul className="faq-modal__list">
              {[...FAQ_list, ...FAQ_more].map((item, idx) => (
                <li key={item.id} className="faq-modal__item">
                  <span className="faq-modal__number">Q{idx + 1}.</span>
                  <div className="faq-modal__content">
                    <p className="faq-modal__question">{item.q}</p>
                    <p className="faq-modal__answer">{item.a}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
};

export default FAQs;
