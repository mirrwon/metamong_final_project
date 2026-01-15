import "../../pages/Home.css";

const FAQ_list = [
  {
    id: 1,
    q: "식물을 잘 몰라도 사용할 수 있나요?",
    a: "네! AI가 사용자의 공간과 취향을 바탕으로 추천해요.",
  },
  {
    id: 2,
    q: "사진은 꼭 올려야 하나요?",
    a: "아니요. 선택 사항이에요. 사진을 올리면 더 정확해요.",
  },
  {
    id: 3,
    q: "추천 결과는 어떻게 활용하면 되나요?",
    a: "추천된 식물을 참고해 배치 아이디어를 얻고, 나만의 공간을 계획하는 데 활용할 수 있어요.",
  },
];

const FAQs = () => {
  return (
    <section className="faq">
      <h2 className="faq__title">🌱FAQ. 이런 점이 궁금했어요</h2>

      <ul className="faq__list">
        {FAQ_list.map((item) => (
          <li key={item.id} className="faq__item">
            <p className="faq__question">{item.q}</p>
            <p className="faq__answer">{item.a}</p>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default FAQs;
