import ProcessCarousel from "../components/home/ProcessCarousel";
import FAQs from "../components/home/FAQs";
import PlantPreview from "../components/home/PlantPreview";
import "./Home.css";

const Home = () => {
  const sharedAutoplayDelay = 2500;
  // const nav = useNavigate();

  // const goChat = () => {
  //   nav(ROUTES.CHAT)
  // }

  return (
    <div className="home">
      <section className="home-section">
        <ProcessCarousel autoplayDelay={sharedAutoplayDelay} />
      </section>

      <section className="home-section home-plants">
        <h2 className="typo-title">Plant Catalog</h2>
        <div className="ui-line" />
        <PlantPreview autoplayDelay={sharedAutoplayDelay} />
      </section>

      <section className="home-section">
        <FAQs />
      </section>

    </div>
  );
};

export default Home;
