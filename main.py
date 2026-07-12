"""
Mini servicio web para el generador de DMA — pensado para ser llamado desde Make.com.

Endpoints:
  POST /extraer   -> recibe un PDF (certificado nacimiento o matrimonio), devuelve JSON con los datos.
  POST /generar    -> recibe el JSON completo del caso, devuelve el archivo .docx generado.
  GET  /            -> healthcheck.

Despliegue en Render.com (gratis, sin terminal):
  1. Sube esta carpeta a un repo de GitHub (arrastrar y soltar archivos en github.com funciona).
  2. En render.com -> "New +" -> "Web Service" -> conecta el repo.
  3. Render detecta el Dockerfile automáticamente. Deploy.
  4. Copia la URL que te da Render (ej. https://generador-dma.onrender.com) y úsala en Make.
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from docxtpl import DocxTemplate
from extractor_certificados import extraer_certificado
import tempfile
import io
import os

app = FastAPI(title="Generador DMA - Acción Jurídica")

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "DMA_Template.docx")


@app.get("/")
def healthcheck():
    return {"status": "ok", "servicio": "Generador DMA - Acción Jurídica"}


@app.post("/extraer")
async def extraer(file: UploadFile = File(...)):
    """Recibe un certificado PDF (nacimiento o matrimonio) y devuelve los datos extraídos."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "El archivo debe ser un PDF")

    contenido = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(contenido)
        tmp_path = tmp.name

    try:
        datos = extraer_certificado(tmp_path)
    except ValueError as e:
        raise HTTPException(422, str(e))
    finally:
        os.unlink(tmp_path)

    return datos


class GenerarRequest(BaseModel):
    # Se recibe tal cual el JSON de contexto para docxtpl.
    # No se valida campo por campo a propósito: la plantilla ya maneja
    # ausencias/condicionales, y así Make puede mandar el JSON crudo de Airtable.
    context: Dict[str, Any]


@app.post("/generar")
def generar(payload: GenerarRequest):
    """Recibe el contexto completo del caso y devuelve el .docx generado."""
    if not os.path.exists(TEMPLATE_PATH):
        raise HTTPException(500, "No se encontró DMA_Template.docx en el servidor")

    tpl = DocxTemplate(TEMPLATE_PATH)
    try:
        tpl.render(payload.context)
    except Exception as e:
        raise HTTPException(422, f"Error al renderizar la plantilla: {e}")

    buf = io.BytesIO()
    tpl.save(buf)
    buf.seek(0)

    nombre_dte = payload.context.get("demandante", {}).get("nombre", "caso").split(" ")[0]
    nombre_ddo = payload.context.get("demandado", {}).get("nombre", "").split(" ")[0]
    filename = f"DMA_{nombre_dte}_{nombre_ddo}.docx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
