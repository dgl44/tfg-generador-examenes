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


_OUTPUT_REVISAR = (
    "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) "
    "seguido de un comentario detallado."
)


# Criterio común de veredicto: empuja al revisor a mojarse en lugar de refugiarse
# en "APROBADA CON SUGERENCIAS" ante un defecto real.
_CRITERIO_VEREDICTO = (
    "Sé exigente y mójate con el veredicto; no te quedes en un término medio "
    "cómodo:\n"
    "- RECHAZADA: si la pregunta o su respuesta tienen cualquier defecto que las "
    "haga no aptas tal cual (error técnico, respuesta marcada incorrecta, "
    "ambigüedad, enunciado confuso, ninguna o más de una opción correcta, o "
    "dificultad inadecuada). Ante la duda sobre su corrección, RECHAZADA.\n"
    "- APROBADA CON SUGERENCIAS: solo si la pregunta YA es válida y utilizable tal "
    "cual, y tus comentarios son mejoras opcionales de estilo o redacción.\n"
    "- APROBADA: si es correcta y no necesita cambios.\n"
    "Empieza tu respuesta con una línea exactamente así:\n"
    "VEREDICTO: <APROBADA | APROBADA CON SUGERENCIAS | RECHAZADA>"
)


def _codigo_plano(unidad: UnidadCodigo) -> str:
    docstring_info = f"\nDocstring: {unidad.docstring}" if unidad.docstring else ""
    return f"{docstring_info}\n\nCódigo:\n```\n{unidad.codigo}\n```"


def _bloque_codigo_generador(unidad: UnidadCodigo) -> str:
    """Código para el generador, con la instrucción de no reproducirlo."""
    return (
        "\n\nEl siguiente código es únicamente para tu análisis. NO lo "
        "reproduzcas ni lo cites textualmente en el enunciado: se mostrará al "
        "estudiante junto a la pregunta. (Sí puedes incluir llamadas o "
        "fragmentos nuevos que la pregunta necesite, como una secuencia de "
        "ejecución a trazar.)"
        f"{_codigo_plano(unidad)}"
    )


def _bloque_codigo_revisor(unidad: UnidadCodigo) -> str:
    """Código para el revisor, para que pueda verificar la corrección."""
    return (
        "El código de la unidad sobre la que trata la pregunta es el "
        "siguiente, y se mostrará también al estudiante junto al enunciado. "
        "Úsalo para verificar la corrección técnica de la pregunta y de su "
        "respuesta. NO consideres un defecto que el enunciado no reproduzca el "
        "código: el estudiante lo tendrá delante."
        f"{_codigo_plano(unidad)}\n\n"
    )


def _prompts_test(unidad, tipo_str, codigo_gen, codigo_rev, desc, nivel) -> PromptsPregunta:
    return PromptsPregunta(
        desc_generar=(
            f"Contexto: pregunta para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}' y genera "
            "UNA pregunta tipo test con 4 opciones (A, B, C, D), donde solo una "
            f"es correcta. La pregunta debe evaluar comprensión a nivel {nivel}, "
            "no sintaxis trivial. Indica la respuesta correcta y justifica brevemente."
            f"{codigo_gen}"
        ),
        output_generar=(
            "Una pregunta tipo test con enunciado claro, 4 opciones etiquetadas "
            "A-D, la respuesta correcta indicada y una justificación breve."
        ),
        desc_revisar=(
            f"Contexto: la pregunta es para {desc}.\n\n"
            f"{codigo_rev}"
            "Revisa la pregunta evaluando:\n"
            "1. ¿El enunciado es claro y preciso?\n"
            "2. ¿Las 4 opciones están bien planteadas (una correcta inequívoca, "
            "distractores plausibles)?\n"
            "3. ¿La respuesta marcada es realmente correcta dado el código?\n"
            "4. ¿La justificación del generador es correcta?\n"
            f"5. ¿El nivel de dificultad es apropiado para {desc}? "
            "Rechaza preguntas trivialmente obvias para ese nivel.\n\n"
            + _CRITERIO_VEREDICTO
        ),
        output_revisar=_OUTPUT_REVISAR,
    )


def _prompts_traza(unidad, tipo_str, codigo_gen, codigo_rev, desc, nivel) -> PromptsPregunta:
    return PromptsPregunta(
        desc_generar=(
            f"Contexto: pregunta de traza para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}'. "
            "Formula UNA pregunta de razonamiento sobre ejecución: proporciona "
            "una llamada concreta con argumentos reales e indica qué debe responder "
            "el estudiante (valor de retorno, valor de una variable en un punto dado, "
            "o salida impresa). Incluye la respuesta correcta y explica el razonamiento "
            "paso a paso."
            f"{codigo_gen}"
        ),
        output_generar=(
            "Enunciado con la llamada concreta, pregunta clara sobre el resultado "
            "de la ejecución, respuesta correcta y razonamiento paso a paso."
        ),
        desc_revisar=(
            f"Contexto: pregunta de traza para {desc}.\n\n"
            f"{codigo_rev}"
            "Revisa la pregunta evaluando:\n"
            "1. ¿La llamada de ejemplo es válida para el código dado?\n"
            "2. ¿La respuesta esperada es determinista e inequívoca?\n"
            "3. ¿El razonamiento paso a paso es correcto?\n"
            f"4. ¿La dificultad es adecuada para nivel {nivel}?\n\n"
            + _CRITERIO_VEREDICTO
        ),
        output_revisar=_OUTPUT_REVISAR,
    )


def _prompts_abierta(unidad, tipo_str, codigo_gen, codigo_rev, desc, nivel) -> PromptsPregunta:
    return PromptsPregunta(
        desc_generar=(
            f"Contexto: pregunta abierta para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}'. "
            "Formula UNA pregunta abierta corta que requiera al estudiante "
            "demostrar que COMPRENDE el código: explicar qué hace un bloque concreto "
            "y con qué fin, justificar por qué se ha resuelto de la manera en que "
            "está escrito, o describir el efecto de una parte del código sobre los "
            "datos. NO pidas proponer mejoras, refactorizaciones ni identificar "
            "limitaciones o defectos: el objetivo es evaluar la comprensión del "
            "código tal como está, no que el estudiante lo modifique o lo critique. "
            "Incluye una respuesta modelo orientativa."
            f"{codigo_gen}"
        ),
        output_generar=(
            "Pregunta abierta con enunciado claro y una respuesta modelo orientativa "
            "que el docente puede usar como referencia para la corrección."
        ),
        desc_revisar=(
            f"Contexto: pregunta abierta para {desc}.\n\n"
            f"{codigo_rev}"
            "Revisa la pregunta evaluando:\n"
            "1. ¿El enunciado está bien delimitado (no es demasiado vago)?\n"
            "2. ¿La respuesta modelo es técnicamente correcta?\n"
            "3. ¿La pregunta requiere comprensión real del código, no solo lectura "
            "superficial?\n"
            f"4. ¿La dificultad es adecuada para nivel {nivel}?\n"
            "5. ¿Se limita a evaluar la comprensión del código tal como está, sin "
            "pedir mejoras, refactorizaciones ni identificar limitaciones o "
            "defectos? Si las pide, recházala.\n\n"
            + _CRITERIO_VEREDICTO
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
    tipo_str = {"funcion": "función", "metodo": "método"}.get(unidad.tipo, "clase")
    codigo_gen = _bloque_codigo_generador(unidad)
    codigo_rev = _bloque_codigo_revisor(unidad)
    constructor = _CONSTRUCTORES[tipo_pregunta]
    return constructor(unidad, tipo_str, codigo_gen, codigo_rev, desc, nivel)
