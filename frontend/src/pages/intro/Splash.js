import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './Splash.css';

const Splash = () => {
  const nav = useNavigate();

  useEffect(() => {
    const timer = setTimeout(() => {
      nav('/home');
    }, 2000);

    return () => clearTimeout(timer);
  }, [nav]);

  return (
  <div className="splash">
    <p className="typo-muted typo-sm splash-desc">
      나의 공간에 맞는, 내가 원하는 식물을 쉽게 찾아주는 AI
    </p>

    <div className="ui-line splash-line" />

    <h1 className="typo-title typo-xl splash-title">Ditto</h1>

    <div className="splash-image-wrap">
      <img className="ui-photo" src="/images/cover.jpg" alt="cover" />
    </div>
  </div>
);

};

export default Splash;
