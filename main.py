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
from docxtpl import DocxTemplate, RichText
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

    context = payload.context
    hijos = context.get("hijos") or []

    # Airtable/Make manda las keys de cada hijo en PascalCase con prefijo
    # "Hijo" (HijoNombre, HijoRUT, HijoDomicilio, HijoFechaNacimiento,
    # HijoEdad, HijoGenero). El resto de esta función usa snake_case sin
    # prefijo (nombre, rut, domicilio, fecha_nacimiento, edad, genero) —
    # se traduce acá, una sola vez, para no depender de cómo esté
    # configurado el Array Aggregator en Make.
    MAPA_KEYS_HIJO = {
        "HijoNombre": "nombre",
        "HijoRUT": "rut",
        "HijoDomicilio": "domicilio",
        "HijoFechaNacimiento": "fecha_nacimiento",
        "HijoEdad": "edad",
        "HijoGenero": "genero",
    }
    hijos_normalizados = []
    for h in hijos:
        h_norm = dict(h)
        for key_original, key_nueva in MAPA_KEYS_HIJO.items():
            if key_original in h_norm:
                h_norm[key_nueva] = h_norm.pop(key_original)
        hijos_normalizados.append(h_norm)
    hijos = hijos_normalizados
    context["hijos"] = hijos

    # Airtable puede mandar null en campos vacíos (ej. domicilio no
    # disponible en el certificado de nacimiento, ya que este tipo de
    # certificado no trae esa información). Sin este saneo, Jinja2
    # imprime el texto literal "None" en vez de dejarlo vacío.
    for h in hijos:
        for key in h:
            if h[key] is None:
                h[key] = ""

    # Normaliza "edad" a entero: si llega como texto desde Airtable/Make
    # (ej. "15" en vez de 15), la comparación "hijo.edad < 18" dentro de
    # la plantilla puede fallar o comportarse mal al comparar texto con
    # número. Se hace acá, una sola vez, para todo el documento.
    for h in hijos:
        try:
            h["edad"] = int(h.get("edad") or 0)
        except (ValueError, TypeError):
            h["edad"] = 0

    context["todos_hijos_mayores"] = bool(hijos) and all(
        h["edad"] >= 18 for h in hijos
    )

    # Si no se especifica, por defecto SÍ se incluye la cláusula de gastos
    # extraordinarios (Ley 14.908) — se puede desactivar por caso pasando
    # "gastos_extraordinarios_aplica": false cuando no corresponda.
    if "gastos_extraordinarios_aplica" not in context:
        context["gastos_extraordinarios_aplica"] = True

    # Arma la lista numerada de documentos del SEGUNDO OTROSÍ dinámicamente,
    # para que la numeración sea siempre correcta sin importar cuántos hijos,
    # testigos, o condiciones (mediación, informe de cese, etc.) apliquen
    # en este caso. Los nombres de personas van en negrita (RichText) y en
    # mayúscula. Los ítems sin dato real (ej. informe de cese no aportado)
    # se omiten en vez de mostrarse vacíos.
    demandante = context.get("demandante") or {}
    demandado = context.get("demandado") or {}
    alimentos = context.get("alimentos") or {}
    rdr = context.get("relacion_directa_regular") or {}
    testigos = context.get("testigos") or []

    # docxtpl RichText NO hereda la fuente/tamaño del documento — hay que
    # especificarlo en cada .add() o queda con la fuente por defecto de
    # Word (Calibri 11), distinta al resto del documento (Times New Roman
    # 12pt / tamaño 24 en semi-puntos).
    FUENTE = "Times New Roman"
    TAMANO = 24  # 12pt, en semi-puntos (unidad que usa python-docx/docxtpl)

    def doc_simple(texto):
        rt = RichText()
        rt.add(texto, font=FUENTE, size=TAMANO)
        return rt

    def doc_con_nombre_bold(antes, nombre, despues):
        rt = RichText()
        rt.add(antes, font=FUENTE, size=TAMANO)
        rt.add((nombre or "").upper(), bold=True, font=FUENTE, size=TAMANO)
        rt.add(despues, font=FUENTE, size=TAMANO)
        return rt

    docs = []
    docs.append(doc_simple(
        "Acta de acuerdo regulatorio de relaciones mutuas suscrito entre los "
        "comparecientes, para su aprobación judicial."
    ))
    docs.append(doc_con_nombre_bold(
        "Certificado de matrimonio entre ", demandante.get("nombre"), ""
    ))
    docs[-1].add(" y ", font=FUENTE, size=TAMANO)
    docs[-1].add((demandado.get("nombre") or "").upper(), bold=True, font=FUENTE, size=TAMANO)
    docs[-1].add(".", font=FUENTE, size=TAMANO)

    fecha_informe_cese = (context.get("fecha_informe_cese") or "").strip()
    if fecha_informe_cese and fecha_informe_cese.upper() != "XXXXXX":
        docs.append(doc_simple(f"Informe de Cese de convivencia de fecha {fecha_informe_cese}."))

    for hijo in hijos:
        nombre_hijo = (hijo.get("nombre") or "").strip()
        if nombre_hijo:
            docs.append(doc_con_nombre_bold("Certificado de nacimiento de ", nombre_hijo, "."))

    if alimentos.get("tipo") == "mediacion_previa" or rdr.get("tipo") == "mediacion_previa":
        # Se usan los datos de alimentos si existen; si no, los de RDR.
        fuente = alimentos if alimentos.get("tipo") == "mediacion_previa" else rdr
        fecha_mediacion = fuente.get("fecha_mediacion", "")
        fecha_resolucion = fuente.get("fecha_resolucion", "")
        rit = fuente.get("rit", "")
        tribunal_origen = fuente.get("tribunal_origen", "")
        docs.append(doc_simple(f"Acta de mediación de fecha {fecha_mediacion}."))
        docs.append(doc_simple(
            f"Resolución que aprueba mediación de fecha {fecha_resolucion}, "
            f"dictada en causa RIT {rit} del Juzgado de Familia de {tribunal_origen}."
        ))

    for testigo in testigos:
        nombre_testigo = (testigo.get("nombre") or "").strip()
        if nombre_testigo:
            docs.append(doc_con_nombre_bold(
                "Declaración jurada de testigo de ", nombre_testigo,
                ", suscrita con firma electrónica simple mediante Oficina Judicial "
                "Virtual, de acuerdo a lo dispuesto en el inciso final del artículo "
                "64 bis de la ley 19.968."
            ))

    docs.append(doc_simple(
        "Certificado de IUS POSTULANDI vigente de la estudiante habilitada en "
        "Derecho KARIN PAZ VALENZUELA AGUILAR."
    ))

    context["documentos_acompanados"] = docs

    tpl = DocxTemplate(TEMPLATE_PATH)
    try:
        tpl.render(context)
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
