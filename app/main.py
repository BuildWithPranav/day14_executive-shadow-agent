import uvicorn

from app.config import get_settings


def run() -> None:
    """Start the FastAPI server."""

    settings = get_settings()
    uvicorn.run(
        "app.api:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment.lower() == "development",
    )


if __name__ == "__main__":
    run()
