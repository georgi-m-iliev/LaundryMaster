let seconds = 0;
let minutes = 0;
let hours = 0;

function updateTime() {
    seconds++;
    if (seconds === 60) {
        seconds = 0;
        minutes++;
        if (minutes === 60) {
            minutes = 0;
            hours++;
        }
    }
    updateDisplay();
}

function updateDisplay() {
    const display = document.getElementById('display');
    display.textContent = `${formatTime(hours)}:${formatTime(minutes)}:${formatTime(seconds)}`;
}

function formatTime(value) {
    return (value < 10) ? `0${value}` : value;
}

function setStartingTime() {
    const timeParts = document.getElementById('display').textContent.split(':');
    if (timeParts.length === 3) {
        hours = parseInt(timeParts[0]);
        minutes = parseInt(timeParts[1]);
        seconds = parseInt(timeParts[2]);
        clearInterval(); // Stop the current timer (if any)
    }
}

function initStopwatch() {
    console.log("Initializing stopwatch...")
    if(document.getElementById('display').textContent === "None") {
        console.log("No stopwatch to initialize");
        document.getElementById('display').textContent = "00:00:00";
        return;
    }
    setStartingTime();
    setInterval(updateTime, 1000);
}

initStopwatch();
