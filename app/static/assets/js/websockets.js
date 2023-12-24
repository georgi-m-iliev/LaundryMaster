const loc = window.location;
let ws_uri_base;
if (loc.protocol === "https:") {
    ws_uri_base = "wss:";
} else {
    ws_uri_base = "ws:";
}
ws_uri_base += "//" + loc.host;

export const washingMachineInfoWS = new WebSocket(ws_uri_base + "/api/washing_machine_infos");
