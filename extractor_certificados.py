"""
Extractor de datos desde certificados del Registro Civil (Chile) en PDF.
Soporta: CERTIFICADO DE NACIMIENTO y CERTIFICADO DE MATRIMONIO.

Uso:
    from extractor_certificados import extraer_certificado
    data = extraer_certificado("ruta/al/certificado.pdf")
    # data["tipo"] == "nacimiento" | "matrimonio"
"""
import re
import pdfplumber


def _texto_pdf(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _campo(texto, etiqueta, hasta=None):
    """Extrae el valor después de 'etiqueta :' hasta el próximo salto de línea
    o hasta que aparezca la etiqueta 'hasta' (para campos en la misma línea)."""
    if hasta:
        patron = rf"{etiqueta}\s*:\s*(.+?)\s+{hasta}\s*:"
    else:
        patron = rf"{etiqueta}\s*:\s*(.+?)(?:\n|$)"
    m = re.search(patron, texto)
    return m.group(1).strip() if m else None


def _calcular_edad(fecha_nacimiento_str):
    """fecha_nacimiento_str tipo '21 Diciembre 2021' -> edad en años a la fecha actual."""
    from datetime import date
    meses = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", fecha_nacimiento_str)
    if not m:
        return None
    dia, mes_txt, anio = m.groups()
    mes = meses.get(mes_txt.lower())
    if not mes:
        return None
    nacimiento = date(int(anio), mes, int(dia))
    hoy = date.today()
    edad = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
    return edad


def _titulo(s):
    """MARIO ALEXIS MEDINA URIBE -> Mario Alexis Medina Uribe (para insertar en el escrito)."""
    return s.title() if s else s


def extraer_nacimiento(texto):
    circunscripcion = _campo(texto, "Circunscripción")
    nro_inscripcion = _campo(texto, "Nro\\. inscripción", hasta="Registro")
    anio = _campo(texto, "Año")
    nombre = _campo(texto, "Nombre inscrito")
    run = _campo(texto, "R\\.U\\.N\\.")
    fecha_nac = _campo(texto, "Fecha nacimiento")
    sexo = _campo(texto, "Sexo")

    genero = "F" if sexo and sexo.strip().lower().startswith("fem") else "M"

    return {
        "tipo": "nacimiento",
        "nombre": _titulo(nombre),
        "rut": run,
        "fecha_nacimiento": fecha_nac,
        "edad": _calcular_edad(fecha_nac) if fecha_nac else None,
        "genero": genero,
        "circunscripcion_nacimiento": circunscripcion,
        "nro_inscripcion_nacimiento": nro_inscripcion,
        "anio_inscripcion_nacimiento": anio,
        # domicilio NO viene en el certificado: se completa manualmente
        "domicilio": None,
    }


def extraer_matrimonio(texto):
    circunscripcion = _campo(texto, "Circunscripción")
    nro_inscripcion = _campo(texto, "Nro\\. inscripción", hasta="Registro")
    anio = _campo(texto, "Año")
    marido = _campo(texto, "Nombre del Marido")
    run_marido = re.search(r"Nombre del Marido.*?\n.*?R\.U\.N\.\s*:\s*([\d.\-Kk]+)", texto)
    mujer = _campo(texto, "Nombre de la Mujer")
    fecha_celebracion = _campo(texto, "FECHA CELEBRACIÓN")

    # RUNs: el primero que aparece tras "Nombre del Marido" es del marido,
    # el segundo (tras "Nombre de la Mujer") es de la mujer.
    runs = re.findall(r"R\.U\.N\.\s*:\s*([\d.\-Kk]+)", texto)
    run_m = runs[0] if len(runs) > 0 else None
    run_w = runs[1] if len(runs) > 1 else None

    return {
        "tipo": "matrimonio",
        "circunscripcion": circunscripcion,
        "numero_inscripcion": nro_inscripcion,
        "anio_inscripcion": anio,
        "fecha": fecha_celebracion.split(" A LAS")[0].strip() if fecha_celebracion else None,
        "conyuge_marido": {"nombre": _titulo(marido), "rut": run_m},
        "conyuge_mujer": {"nombre": _titulo(mujer), "rut": run_w},
    }


def extraer_certificado(path):
    texto = _texto_pdf(path)
    if "CERTIFICADO DE NACIMIENTO" in texto:
        return extraer_nacimiento(texto)
    elif "CERTIFICADO DE MATRIMONIO" in texto:
        return extraer_matrimonio(texto)
    else:
        raise ValueError(f"Tipo de certificado no reconocido en {path}")


if __name__ == "__main__":
    import json
    import sys
    for p in sys.argv[1:]:
        print(f"--- {p} ---")
        print(json.dumps(extraer_certificado(p), ensure_ascii=False, indent=2))
