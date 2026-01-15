import { useNavigate } from "react-router-dom";
import ProcessCarousel from "../components/home/ProcessCarousel";
import FAQs from "../components/home/FAQs";
import { ROUTES } from "../constants/routes";
import "./Home.css";

const Home = () => {
  const nav = useNavigate();

  const goChat = () => {
    nav(ROUTES.CHAT)
  }


  return (
    <div className="home">
   
      <ProcessCarousel />
      
      
      {/* <Button text="Start" type="primary" onClick={goChat} /> */}
     
      <FAQs />

    </div>
  );
};

export default Home;
