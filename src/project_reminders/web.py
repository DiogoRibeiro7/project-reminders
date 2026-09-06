"""Small server-rendered local dashboard."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from project_reminders.application.dashboard import build_dashboard
from project_reminders.bootstrap import build_service
from project_reminders.domain.enums import HealthDimension

_TEMPLATE_DIR = Path(__file__).with_name("templates")


def create_app(root: Path | None = None) -> FastAPI:
    """Create the local web application for one project-reminders root."""

    project_root = root or Path.cwd()
    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml")),
    )
    app = FastAPI(title="project-reminders", docs_url="/api/docs")

    @app.get("/", response_class=HTMLResponse)
    def dashboard_page() -> HTMLResponse:
        service = build_service(project_root)
        dashboard = build_dashboard(service.load())
        template = environment.get_template("dashboard.html")
        return HTMLResponse(template.render(dashboard=dashboard, dimensions=tuple(HealthDimension)))

    @app.get("/projects/{identifier}", response_class=HTMLResponse)
    def project_page(identifier: str) -> HTMLResponse:
        service = build_service(project_root)
        try:
            project = service.find(identifier)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        template = environment.get_template("project.html")
        return HTMLResponse(template.render(project=project, dimensions=tuple(HealthDimension)))

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
