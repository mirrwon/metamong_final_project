const Button = ({ text, type, onClick, value }) => {
    return (
        <button value = {value} onClick={onClick} className={`Button Button_${type}`}> 
            {text}
        </button>
    )
}

export default Button;

