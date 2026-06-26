"""Utilidades compartidas por los generadores de examen (PDF y Word).

Transforman el texto que produce el modelo en el enunciado que ve el alumno:
recortan la solución y limpian el marcado Markdown. Centralizarlas evita
duplicar esta lógica entre los distintos formatos de salida.
"""

import re

# Marcadores tras los cuales el texto del modelo deja de ser enunciado y pasa
# a ser solución. Se busca el primero que aparezca y se corta ahí.
_MARCADORES_SOLUCION = (
    "respuesta correcta", "respuesta modelo", "solución", "solucion",
    "justificación", "justificacion", "razonamiento paso a paso",
)


def _solo_enunciado(texto: str) -> str:
    """Recorta la solución, dejando únicamente el enunciado para el alumno."""
    bajo = texto.lower()
    corte = len(texto)
    for marcador in _MARCADORES_SOLUCION:
        pos = bajo.find(marcador)
        if pos != -1:
            corte = min(corte, pos)
    return texto[:corte].rstrip()


def _limpiar_markdown(texto: str) -> str:
    """Elimina el marcado Markdown más común que produce el modelo."""
    lineas = []
    for linea in texto.splitlines():
        despojada = linea.strip()
        if despojada.startswith("```"):
            continue  # se omiten las vallas de bloque de código
        # Separadores horizontales (---, ***, ___)
        if len(despojada) >= 3 and set(despojada) <= {"-", "*", "_"}:
            continue
        if linea.lstrip().startswith("#"):
            linea = linea.lstrip("#").strip()
        # Quita negritas (pares **...**) sin tocar '**' del código (p. ej. n**0.5)
        linea = re.sub(r"\*\*(.+?)\*\*", r"\1", linea)
        linea = linea.replace("`", "")
        lineas.append(linea)
    # Colapsa líneas en blanco consecutivas
    salida: list[str] = []
    for linea in lineas:
        if not linea.strip() and salida and not salida[-1].strip():
            continue
        salida.append(linea)
    return "\n".join(salida).strip()


def enunciado_visible(texto: str) -> str:
    """Devuelve el enunciado listo para el examen del alumno (sin solución)."""
    return _limpiar_markdown(_solo_enunciado(texto))


def incluye_codigo(enunciado: str, codigo: str) -> bool:
    """Indica si el enunciado ya reproduce el código de la unidad.

    Sirve para no adjuntar el código por segunda vez cuando el modelo, pese a
    las instrucciones, lo ha incrustado en el enunciado. Se compara la firma
    (primera línea no vacía: ``def ...``/``class ...``) normalizando espacios.
    """
    lineas = [ln for ln in codigo.strip().splitlines() if ln.strip()]
    if not lineas:
        return False
    firma = " ".join(lineas[0].split())
    return firma in " ".join(enunciado.split())


def titulo_examen(titulo: str | None, asignatura: str) -> str:
    """Determina el título del examen, con un valor por defecto razonable."""
    if titulo and titulo.strip():
        return titulo.strip()
    return f"Examen de {asignatura}"
