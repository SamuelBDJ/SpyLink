from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from database import get_connection, init_db


app = FastAPI(title="Spy-Link")

init_db()

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(directory="templates")


# =========================================================
# MODELOS DOS DADOS DE LOCALIZAÇÃO
# =========================================================

class LocationData(BaseModel):
    consent_given: int = 1
    latitude: float
    longitude: float
    accuracy: float | None = None


class LocationErrorData(BaseModel):
    consent_given: int = 1
    location_error: str | None = None


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    connection = get_connection()

    active_projects = connection.execute(
        "SELECT COUNT(*) FROM projects WHERE active = 1"
    ).fetchone()[0]

    total_accesses = connection.execute(
        "SELECT COUNT(*) FROM access_logs"
    ).fetchone()[0]

    shared_locations = connection.execute(
        """
        SELECT COUNT(*)
        FROM access_logs
        WHERE location_status = 'success'
        """
    ).fetchone()[0]

    connection.close()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_projects": active_projects,
            "total_accesses": total_accesses,
            "shared_locations": shared_locations
        }
    )


# =========================================================
# LISTAGEM DE PROJETOS
# =========================================================

@app.get("/projects", response_class=HTMLResponse)
def projects(request: Request):
    connection = get_connection()

    projects = connection.execute(
        "SELECT * FROM projects ORDER BY id DESC"
    ).fetchall()

    connection.close()

    return templates.TemplateResponse(
        request=request,
        name="projects.html",
        context={
            "request": request,
            "projects": projects
        }
    )


# =========================================================
# NOVO PROJETO
# =========================================================

@app.get("/projects/new", response_class=HTMLResponse)
def new_project(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="project_new.html"
    )


@app.post("/projects")
def create_project(
    name: str = Form(...),
    slug: str = Form(...),
    destination_url: str = Form(...),
    description: str = Form(""),
    location_enabled: str | None = Form(None)
):
    connection = get_connection()

    connection.execute(
        """
        INSERT INTO projects (
            name,
            slug,
            destination_url,
            description,
            location_enabled
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            name,
            slug,
            destination_url,
            description,
            1 if location_enabled else 0
        )
    )

    connection.commit()
    connection.close()

    return RedirectResponse(
        url="/projects",
        status_code=303
    )


# =========================================================
# EDITAR PROJETO
# =========================================================

@app.get("/projects/{project_id}/edit", response_class=HTMLResponse)
def edit_project_page(project_id: int, request: Request):
    connection = get_connection()

    project = connection.execute(
        "SELECT * FROM projects WHERE id = ?",
        (project_id,)
    ).fetchone()

    connection.close()

    if project is None:
        return HTMLResponse(
            content="Projeto não encontrado",
            status_code=404
        )

    return templates.TemplateResponse(
        request=request,
        name="project_edit.html",
        context={
            "request": request,
            "project": project
        }
    )


@app.post("/projects/{project_id}/edit")
def update_project(
    project_id: int,
    name: str = Form(...),
    slug: str = Form(...),
    destination_url: str = Form(...),
    description: str = Form(""),
    location_enabled: str | None = Form(None)
):
    connection = get_connection()

    connection.execute(
        """
        UPDATE projects
        SET
            name = ?,
            slug = ?,
            destination_url = ?,
            description = ?,
            location_enabled = ?
        WHERE id = ?
        """,
        (
            name,
            slug,
            destination_url,
            description,
            1 if location_enabled else 0,
            project_id
        )
    )

    connection.commit()
    connection.close()

    return RedirectResponse(
        url="/projects",
        status_code=303
    )


# =========================================================
# EXCLUIR PROJETO
# =========================================================

@app.post("/projects/{project_id}/delete")
def delete_project(project_id: int):
    connection = get_connection()

    connection.execute(
        "DELETE FROM projects WHERE id = ?",
        (project_id,)
    )

    connection.commit()
    connection.close()

    return RedirectResponse(
        url="/projects",
        status_code=303
    )


# =========================================================
# PÁGINA PÚBLICA DO PROJETO
# =========================================================

@app.get("/p/{slug}", response_class=HTMLResponse)
def public_project(slug: str, request: Request):
    connection = get_connection()

    project = connection.execute(
        """
        SELECT *
        FROM projects
        WHERE slug = ?
        AND active = 1
        """,
        (slug,)
    ).fetchone()

    connection.close()

    if project is None:
        return HTMLResponse(
            content="Projeto não encontrado",
            status_code=404
        )

    return templates.TemplateResponse(
        request=request,
        name="public_project.html",
        context={
            "request": request,
            "project": project
        }
    )


# =========================================================
# CONTINUAR SEM COMPARTILHAR LOCALIZAÇÃO
# =========================================================

@app.post("/p/{slug}/continue")
def continue_public_project(slug: str, request: Request):
    connection = get_connection()

    project = connection.execute(
        """
        SELECT *
        FROM projects
        WHERE slug = ?
        AND active = 1
        """,
        (slug,)
    ).fetchone()

    if project is None:
        connection.close()

        return HTMLResponse(
            content="Projeto não encontrado",
            status_code=404
        )

    user_agent = request.headers.get("user-agent")

    connection.execute(
        """
        INSERT INTO access_logs (
            project_id,
            consent_given,
            user_agent,
            location_status
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            project["id"],
            0,
            user_agent,
            "denied"
        )
    )

    connection.commit()
    connection.close()

    return RedirectResponse(
        url=project["destination_url"],
        status_code=303
    )


# =========================================================
# LOCALIZAÇÃO OBTIDA COM SUCESSO
# =========================================================

@app.post("/p/{slug}/location")
def receive_location(
    slug: str,
    request: Request,
    data: LocationData
):
    connection = get_connection()

    project = connection.execute(
        """
        SELECT *
        FROM projects
        WHERE slug = ?
        AND active = 1
        """,
        (slug,)
    ).fetchone()

    if project is None:
        connection.close()

        return JSONResponse(
            content={"error": "Projeto não encontrado"},
            status_code=404
        )

    user_agent = request.headers.get("user-agent")

    connection.execute(
        """
        INSERT INTO access_logs (
            project_id,
            consent_given,
            user_agent,
            latitude,
            longitude,
            accuracy,
            location_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project["id"],
            1,
            user_agent,
            data.latitude,
            data.longitude,
            data.accuracy,
            "success"
        )
    )

    connection.commit()
    connection.close()

    return JSONResponse(
        content={
            "redirect_url": project["destination_url"]
        }
    )


# =========================================================
# ERRO AO OBTER LOCALIZAÇÃO
# =========================================================

@app.post("/p/{slug}/location-error")
def receive_location_error(
    slug: str,
    request: Request,
    data: LocationErrorData
):
    connection = get_connection()

    project = connection.execute(
        """
        SELECT *
        FROM projects
        WHERE slug = ?
        AND active = 1
        """,
        (slug,)
    ).fetchone()

    if project is None:
        connection.close()

        return JSONResponse(
            content={"error": "Projeto não encontrado"},
            status_code=404
        )

    user_agent = request.headers.get("user-agent")

    connection.execute(
        """
        INSERT INTO access_logs (
            project_id,
            consent_given,
            user_agent,
            location_status,
            location_error
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            project["id"],
            1,
            user_agent,
            "error",
            data.location_error
        )
    )

    connection.commit()
    connection.close()

    return JSONResponse(
        content={
            "redirect_url": project["destination_url"]
        }
    )


# =========================================================
# DETALHES DO PROJETO
# =========================================================

@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail(project_id: int, request: Request):
    connection = get_connection()

    project = connection.execute(
        """
        SELECT *
        FROM projects
        WHERE id = ?
        """,
        (project_id,)
    ).fetchone()

    if project is None:
        connection.close()

        return HTMLResponse(
            content="Projeto não encontrado",
            status_code=404
        )

    total_accesses = connection.execute(
        """
        SELECT COUNT(*)
        FROM access_logs
        WHERE project_id = ?
        """,
        (project_id,)
    ).fetchone()[0]

    total_consents = connection.execute(
        """
        SELECT COUNT(*)
        FROM access_logs
        WHERE project_id = ?
        AND consent_given = 1
        """,
        (project_id,)
    ).fetchone()[0]

    total_locations = connection.execute(
        """
        SELECT COUNT(*)
        FROM access_logs
        WHERE project_id = ?
        AND location_status = 'success'
        """,
        (project_id,)
    ).fetchone()[0]

    access_logs = connection.execute(
        """
        SELECT *
        FROM access_logs
        WHERE project_id = ?
        ORDER BY created_at DESC
        """,
        (project_id,)
    ).fetchall()

    connection.close()

    public_url = f"/p/{project['slug']}"

    return templates.TemplateResponse(
        request=request,
        name="project_detail.html",
        context={
            "request": request,
            "project": project,
            "total_accesses": total_accesses,
            "total_consents": total_consents,
            "total_locations": total_locations,
            "access_logs": access_logs,
            "public_url": public_url
        }
    )


