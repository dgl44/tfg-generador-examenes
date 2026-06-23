"""Construcción de los prompts de generación y revisión.

Aísla todo el texto en lenguaje natural que se envía a los agentes. Separar
los prompts del resto de la lógica facilita iterar sobre su redacción —una de
las líneas de trabajo futuro de la memoria— sin tocar la orquestación, y
permite versionarlos o compararlos de forma controlada.
"""

from dataclasses import dataclass

from modelos import TipoPregunta
from parser import UnidadCodigo


@dataclass
class PromptsPregunta:
    """Las cuatro piezas de texto que necesita un crew generador+revisor."""
    desc_generar: str
    output_generar: str
    desc_revisar: str
    output_revisar: str


# Nota común a todos los revisores: el código se adjunta aparte en la capa de
# presentación, así que el revisor no debe penalizar su ausencia en el enunciado.
_NOTA_CODIGO_ADJUNTO = (
    "Ten en cuenta que el código de la unidad se mostrará al estudiante "
    "junto al enunciado, por lo que NO debes penalizar que la pregunta "
    "no incluya literalmente el código.\n\n"
)

_OUTPUT_REVISAR = (
    "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) "
    "seguido de un comentario detallado."
)


def _bloque_codigo(unidad: UnidadCodigo) -> str:
    docstring_info = f"\nDocstring: {unidad.docstring}" if unidad.docstring else ""
    return f"{docstring_info}\n\nCódigo:\n```\n{unidad.codigo}\n```"


def _prompts_test(unidad, tipo_str, codigo_bloque, desc, nivel) -> PromptsPregunta:
    return PromptsPregunta(
        desc_generar=(
            f"Contexto: pregunta para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}' y genera "
            "UNA pregunta tipo test con 4 opciones (A, B, C, D), donde solo una "
            f"es correcta. La pregunta debe evaluar comprensión a nivel {nivel}, "
            "no sintaxis trivial. Indica la respuesta correcta y justifica brevemente."
            f"{codigo_bloque}"
        ),
        output_generar=(
            "Una pregunta tipo test con enunciado claro, 4 opciones etiquetadas "
            "A-D, la respuesta correcta indicada y una justificación breve."
        ),
        desc_revisar=(
            f"Contexto: la pregunta es para {desc}.\n\n"
            f"{_NOTA_CODIGO_ADJUNTO}"
            "Revisa la pregunta evaluando:\n"
            "1. ¿El enunciado es claro y preciso?\n"
            "2. ¿Las 4 opciones están bien planteadas (una correcta inequívoca, "
            "distractores plausibles)?\n"
            "3. ¿La respuesta marcada es realmente correcta dado el código?\n"
            "4. ¿La justificación del generador es correcta?\n"
            f"5. ¿El nivel de dificultad es apropiado para {desc}? "
            "Rechaza preguntas trivialmente obvias para ese nivel.\n\n"
            "Veredicto: APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA."
        ),
        output_revisar=_OUTPUT_REVISAR,
    )


def _prompts_traza(unidad, tipo_str, codigo_bloque, desc, nivel) -> PromptsPregunta:
    return PromptsPregunta(
        desc_generar=(
            f"Contexto: pregunta de traza para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}'. "
            "Formula UNA pregunta de razonamiento sobre ejecución: proporciona "
            "una llamada concreta con argumentos reales e indica qué debe responder "
            "el estudiante (valor de retorno, valor de una variable en un punto dado, "
            "o salida impresa). Incluye la respuesta correcta y explica el razonamiento "
            "paso a paso."
            f"{codigo_bloque}"
        ),
        output_generar=(
            "Enunciado con la llamada concreta, pregunta clara sobre el resultado "
            "de la ejecución, respuesta correcta y razonamiento paso a paso."
        ),
        desc_revisar=(
            f"Contexto: pregunta de traza para {desc}.\n\n"
            f"{_NOTA_CODIGO_ADJUNTO}"
            "Revisa la pregunta evaluando:\n"
            "1. ¿La llamada de ejemplo es válida para el código dado?\n"
            "2. ¿La respuesta esperada es determinista e inequívoca?\n"
            "3. ¿El razonamiento paso a paso es correcto?\n"
            f"4. ¿La dificultad es adecuada para nivel {nivel}?\n\n"
            "Veredicto: APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA."
        ),
        output_revisar=_OUTPUT_REVISAR,
    )


def _prompts_abierta(unidad, tipo_str, codigo_bloque, desc, nivel) -> PromptsPregunta:
    return PromptsPregunta(
        desc_generar=(
            f"Contexto: pregunta abierta para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}'. "
            "Formula UNA pregunta abierta corta que requiera al estudiante razonar "
            "sobre el código: explicar una decisión de diseño, describir el propósito "
            "de un bloque concreto, identificar una limitación, o proponer cómo "
            "extenderlo para un nuevo requisito. Incluye una respuesta modelo orientativa."
            f"{codigo_bloque}"
        ),
        output_generar=(
            "Pregunta abierta con enunciado claro y una respuesta modelo orientativa "
            "que el docente puede usar como referencia para la corrección."
        ),
        desc_revisar=(
            f"Contexto: pregunta abierta para {desc}.\n\n"
            f"{_NOTA_CODIGO_ADJUNTO}"
            "Revisa la pregunta evaluando:\n"
            "1. ¿El enunciado está bien delimitado (no es demasiado vago)?\n"
            "2. ¿La respuesta modelo es técnicamente correcta?\n"
            "3. ¿La pregunta requiere comprensión real del código, no solo lectura "
            "superficial?\n"
            f"4. ¿La dificultad es adecuada para nivel {nivel}?\n\n"
            "Veredicto: APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA."
        ),
        output_revisar=_OUTPUT_REVISAR,
    )


# Despacho por tipo de pregunta: añadir un tipo nuevo = registrar su constructor.
_CONSTRUCTORES = {
    TipoPregunta.TEST: _prompts_test,
    TipoPregunta.TRAZA: _prompts_traza,
    TipoPregunta.ABIERTA: _prompts_abierta,
}


def construir_prompts(
    tipo_pregunta: TipoPregunta,
    unidad: UnidadCodigo,
    desc: str,
    nivel: str,
) -> PromptsPregunta:
    """Devuelve las piezas de prompt para generar y revisar una pregunta."""
    tipo_str = "función" if unidad.tipo == "funcion" else "clase"
    codigo_bloque = _bloque_codigo(unidad)
    constructor = _CONSTRUCTORES[tipo_pregunta]
    return constructor(unidad, tipo_str, codigo_bloque, desc, nivel)
