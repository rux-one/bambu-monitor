import ssl
import json
import asyncio
from contextlib import asynccontextmanager

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

_CONFIG_FILE = "config.json"
try:
    with open(_CONFIG_FILE) as _f:
        PRINTERS: list[dict] = json.load(_f)["printers"]
except FileNotFoundError:
    raise SystemExit(f"Missing {_CONFIG_FILE} — copy config.example.json and fill in your printer details.")

PORT = 8883
HTTP_PORT = 8080

PUSH_ALL_CMD = json.dumps({"pushing": {"sequence_id": "1", "command": "pushall"}})

printer_states: dict[str, dict] = {
    p["serial"]: {"name": p["name"], "host": p["host"], "online": False, "data": {}}
    for p in PRINTERS
}
ws_clients: set[WebSocket] = set()
main_loop: asyncio.AbstractEventLoop | None = None


def schedule_broadcast(serial: str) -> None:
    if main_loop is not None:
        main_loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(broadcast(serial))
        )


async def broadcast(serial: str) -> None:
    state = printer_states[serial]
    message = json.dumps({
        "type": "state",
        "serial": serial,
        "name": state["name"],
        "host": state["host"],
        "online": state["online"],
        "data": state["data"],
    })
    dead: set[WebSocket] = set()
    for ws in ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


def make_mqtt_client(printer: dict) -> mqtt.Client:
    serial = printer["serial"]

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"bambu_monitor_{serial}",
    )
    client.username_pw_set("bblp", printer["access_code"])

    tls_ctx = ssl.create_default_context()
    tls_ctx.check_hostname = False
    tls_ctx.verify_mode = ssl.CERT_NONE
    client.tls_set_context(tls_ctx)

    def on_connect(client, userdata, flags, rc, props=None):
        rc_val = rc.value if hasattr(rc, "value") else rc
        printer_states[serial]["online"] = rc_val == 0
        if rc_val == 0:
            client.subscribe(f"device/{serial}/report")
            client.publish(f"device/{serial}/request", PUSH_ALL_CMD)
        schedule_broadcast(serial)

    def on_disconnect(client, userdata, flags, rc, props=None):
        printer_states[serial]["online"] = False
        schedule_broadcast(serial)

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload)
        except json.JSONDecodeError:
            return
        if "print" in data:
            printer_states[serial]["data"].update(data["print"])
            schedule_broadcast(serial)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_running_loop()
    clients = []
    for printer in PRINTERS:
        c = make_mqtt_client(printer)
        c.connect_async(printer["host"], PORT, keepalive=60)
        c.loop_start()
        clients.append(c)
    yield
    for c in clients:
        c.loop_stop()
        c.disconnect()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    for serial, state in printer_states.items():
        await ws.send_text(json.dumps({
            "type": "state",
            "serial": serial,
            "name": state["name"],
            "host": state["host"],
            "online": state["online"],
            "data": state["data"],
        }))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=HTTP_PORT)
