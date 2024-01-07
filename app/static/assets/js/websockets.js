const loc = window.location;
let ws_uri_base;
if (loc.protocol === "https:") {
    ws_uri_base = "wss:";
} else {
    ws_uri_base = "ws:";
}
ws_uri_base += "//" + loc.host;

export function getWS(urlArgs = "") {
    const washingMachineInfoWS = new WebSocket(ws_uri_base + "/api/washing_machine_infos?" + urlArgs);
    washingMachineInfoWS.addEventListener('open', function (event) {
        console.log("Connected to washing machine info websocket");
    });
    return washingMachineInfoWS;
}