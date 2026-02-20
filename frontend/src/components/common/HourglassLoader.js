import "./HourglassLoader.css";

export default function HourglassLoader({ message = "Loading..." }) {
  return (
    <div className="hourglassLoader" role="status" aria-live="polite" aria-busy="true">
      <span className="hourglassLoader__icon" aria-hidden="true" />
      <span className="hourglassLoader__text">{message}</span>
    </div>
  );
}
