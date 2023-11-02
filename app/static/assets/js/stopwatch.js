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
    updateTimeDisplay();
}

function updateTimeDisplay() {
    const display = document.getElementById('time-elapsed');
    display.textContent = `${formatTime(hours)}:${formatTime(minutes)}:${formatTime(seconds)}`;
}

function formatTime(value) {
    return (value < 10) ? `0${value}` : value;
}

function setStartingTime() {
    const timeParts = document.getElementById('time-elapsed').textContent.split(':');
    if (timeParts.length === 3) {
        hours = parseInt(timeParts[0]);
        minutes = parseInt(timeParts[1]);
        seconds = parseInt(timeParts[2]);
        clearInterval(); // Stop the current timer (if any)
    }
}

function initStopwatch() {
    console.log("Initializing stopwatch...")
    if(document.getElementById('time-elapsed').textContent === "None") {
        console.log("No stopwatch to initialize");
        document.getElementById('time-elapsed').textContent = "00:00:00";
        return;
    }
    setStartingTime();
    setInterval(updateTime, 1000);
}

initStopwatch();
