"""Generación del examen en PDF a partir de las preguntas seleccionadas (RF10).

Produce un PDF listo para imprimir o distribuir. Para el examen del alumno se
recorta la solución que el modelo incluye junto al enunciado (ver
:mod:`examen_comun`); el docente la consulta en la interfaz.
"""

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from examen_comun import enunciado_visible, incluye_codigo, titulo_examen
from modelos import ContextoAcademico, ResultadoPregunta

# Tras cada multi_cell, devolver el cursor al margen izquierdo y a la línea
# siguiente, para que el bloque posterior disponga del ancho completo.
_NL = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}


# Rutas candidatas de fuentes Unicode. Se prioriza una fuente incluida en el
# repositorio (si existe) y, en su defecto, las de Windows. Hace falta una
# fuente Unicode porque el texto del modelo contiene acentos, guiones largos
# y comillas latinas que no cubren las fuentes básicas de PDF.
_RAIZ = Path(__file__).resolve().parents[2]
_FUENTES = {
    "regular": [_RAIZ / "recursos" / "fuentes" / "DejaVuSans.ttf",
                Path("C:/Windows/Fonts/arial.ttf")],
    "bold":    [_RAIZ / "recursos" / "fuentes" / "DejaVuSans-Bold.ttf",
                Path("C:/Windows/Fonts/arialbd.ttf")],
    "mono":    [_RAIZ / "recursos" / "fuentes" / "DejaVuSansMono.ttf",
                Path("C:/Windows/Fonts/consola.ttf")],
}


def _primera_existente(rutas: list[Path]) -> Path:
    for ruta in rutas:
        if ruta.exists():
            return ruta
    raise FileNotFoundError(
        f"No se encontró ninguna fuente en: {[str(r) for r in rutas]}"
    )


class _ExamenPDF(FPDF):
    def __init__(self, titulo: str):
        super().__init__()
        self._titulo = titulo
        self.add_font("Cuerpo", "", str(_primera_existente(_FUENTES["regular"])))
        self.add_font("Cuerpo", "B", str(_primera_existente(_FUENTES["bold"])))
        self.add_font("Mono", "", str(_primera_existente(_FUENTES["mono"])))
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font("Cuerpo", "B", 14)
        self.multi_cell(0, 8, self._titulo, align="C", **_NL)
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Cuerpo", "", 8)
        self.cell(0, 8, f"Página {self.page_no()}", align="C")


def generar_examen_pdf(
    resultados: list[ResultadoPregunta],
    contexto: ContextoAcademico | None = None,
    titulo: str | None = None,
) -> bytes:
    """Genera el examen en PDF con las preguntas dadas y lo devuelve en bytes."""
    asignatura = contexto.asignatura if contexto else "Examen"
    pdf = _ExamenPDF(titulo_examen(titulo, asignatura))
    pdf.add_page()

    # Datos del alumno
    pdf.set_font("Cuerpo", "", 11)
    pdf.cell(0, 8, "Nombre y apellidos: ____________________________________")
    pdf.ln(8)
    pdf.cell(0, 8, "Fecha: __________________")
    pdf.ln(12)

    for i, r in enumerate(resultados, start=1):
        pdf.set_font("Cuerpo", "B", 12)
        pdf.multi_cell(0, 7, f"Pregunta {i} ({r.tipo.value})", **_NL)
        pdf.ln(1)

        enunciado = enunciado_visible(r.pregunta_generada)
        pdf.set_font("Cuerpo", "", 11)
        pdf.multi_cell(0, 6, enunciado, **_NL)
        pdf.ln(2)

        # Código de la unidad, salvo que el enunciado ya lo incluya
        if not incluye_codigo(enunciado, r.unidad.codigo):
            pdf.set_font("Cuerpo", "", 10)
            pdf.multi_cell(0, 6, f"Código ({r.unidad.nombre}):", **_NL)
            pdf.set_font("Mono", "", 9)
            pdf.set_fill_color(244, 244, 244)
            pdf.multi_cell(0, 5, r.unidad.codigo, fill=True, **_NL)
        pdf.ln(8)

    return bytes(pdf.output())
