"""Run the local API with the locked-down loopback binding."""

import uvicorn

from .config import settings


if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host=settings.api_host, port=settings.api_port, reload=False)

