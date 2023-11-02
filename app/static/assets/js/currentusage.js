function updateCurrentDisplay() {
    const display = document.getElementById('current-usage');
    fetch('/api/washing_machine/current_energy_consumption').then(
        (response) => {
            return response.json();
        }
    ).then(
        (data) => {
            // console.log(data);
            display.textContent = `${data['value']} W`;
        }
    )
}

function initCurrentUsage() {
    console.log("Initializing current usage monitor...")
    if(document.getElementById('current-usage') == null) {
        console.log("No current usage monitor to initialize");
        document.getElementById('current-usage').textContent = "NaN";
        return;
    }
    setInterval(updateCurrentDisplay, 2000);
}

initCurrentUsage();
