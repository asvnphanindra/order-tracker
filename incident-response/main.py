from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from responder import handle_alert

app = FastAPI(title="Order Tracker Incident Responder")


class AlertPayload(BaseModel):
    alerts: list[dict] = Field(default_factory=list)


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.post("/alerts", status_code=202)
def receive_alert(payload: AlertPayload, background: BackgroundTasks):
    if not payload.alerts:
        raise HTTPException(status_code=400, detail="No alerts received")
    background.add_task(handle_alert, payload.model_dump())
    return {"status": "accepted"}
