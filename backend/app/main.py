from fastapi import FastAPI

app = FastAPI(title="CIVIA API", version="0.0.1-scaffold")


@app.get("/health")
def health():
    return {"status": "ok", "phase": "scaffold"}
