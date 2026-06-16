"""Pipeline que procesa un archivo de código completo.

Combina el parser tree-sitter con el patrón generator-critic: filtra
unidades triviales y, por cada unidad relevante, genera una pregunta
(tipo test, traza de ejecución o abierta) adaptada al contexto académico
y la revisa con un segundo agente.
"""

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Permitir importar otros módulos del mismo directorio cuando se ejecuta
# como script directo (`uv run python src/generador/pipeline_repositorio.py`).
sys.path.insert(0, str(Path(__file__).parent))

from crewai import Agent, Crew, LLM, Process, Task

from parser import UnidadCodigo, extraer_unidades, lenguajes_soportados

llm_haiku = LLM(
    model="bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0",
)


# ------------------------- Tipos de pregunta -------------------------

class TipoPregunta(str, Enum):
    TEST   = "test"    # Opción múltiple con 4 opciones
    TRAZA  = "traza"   # Razonamiento sobre ejecución del código
    ABIERTA = "abierta"  # Pregunta de respuesta libre


# ------------------------- Contexto académico -------------------------

@dataclass
class ContextoAcademico:
    """Parámetros configurables por el docente para adaptar las preguntas."""
    asignatura: str = "Programación"
    curso: str = "2º de Grado"
    titulacion: str = "Ingeniería Informática"
    nivel: str = "intermedio"  # básico | intermedio | avanzado
    tipos_pregunta: list[TipoPregunta] = field(
        default_factory=lambda: [TipoPregunta.TEST]
    )

    def descripcion(self) -> str:
        return (
            f"{self.asignatura} ({self.curso}, {self.titulacion}), "
            f"nivel {self.nivel}"
        )


# ------------------------- Tareas por unidad -------------------------

def _prompts_por_tipo(
    tipo_pregunta: TipoPregunta,
    unidad: UnidadCodigo,
    tipo_str: str,
    docstring_info: str,
    desc: str,
    nivel: str,
) -> tuple[str, str, str, str]:
    """Devuelve (desc_generar, output_generar, desc_revisar, output_revisar)."""
    codigo_bloque = f"{docstring_info}\n\nCódigo:\n```\n{unidad.codigo}\n```"

    if tipo_pregunta == TipoPregunta.TEST:
        desc_gen = (
            f"Contexto: pregunta para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}' y genera "
            "UNA pregunta tipo test con 4 opciones (A, B, C, D), donde solo una "
            f"es correcta. La pregunta debe evaluar comprensión a nivel {nivel}, "
            "no sintaxis trivial. Indica la respuesta correcta y justifica brevemente."
            f"{codigo_bloque}"
        )
        out_gen = (
            "Una pregunta tipo test con enunciado claro, 4 opciones etiquetadas "
            "A-D, la respuesta correcta indicada y una justificación breve."
        )
        desc_rev = (
            f"Contexto: la pregunta es para {desc}.\n\n"
            "Revisa la pregunta evaluando:\n"
            "1. ¿El enunciado es claro y preciso?\n"
            "2. ¿Las 4 opciones están bien planteadas (una correcta inequívoca, "
            "distractores plausibles)?\n"
            "3. ¿La respuesta marcada es realmente correcta dado el código?\n"
            "4. ¿La justificación del generador es correcta?\n"
            f"5. ¿El nivel de dificultad es apropiado para {desc}? "
            "Rechaza preguntas trivialmente obvias para ese nivel.\n\n"
            "Veredicto: APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA."
        )
        out_rev = (
            "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) "
            "seguido de un comentario detallado."
        )

    elif tipo_pregunta == TipoPregunta.TRAZA:
        desc_gen = (
            f"Contexto: pregunta de traza para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}'. "
            "Formula UNA pregunta de razonamiento sobre ejecución: proporciona "
            "una llamada concreta con argumentos reales e indica qué debe responder "
            "el estudiante (valor de retorno, valor de una variable en un punto dado, "
            "o salida impresa). Incluye la respuesta correcta y explica el razonamiento "
            "paso a paso."
            f"{codigo_bloque}"
        )
        out_gen = (
            "Enunciado con la llamada concreta, pregunta clara sobre el resultado "
            "de la ejecución, respuesta correcta y razonamiento paso a paso."
        )
        desc_rev = (
            f"Contexto: pregunta de traza para {desc}.\n\n"
            "Revisa la pregunta evaluando:\n"
            "1. ¿La llamada de ejemplo es válida para el código dado?\n"
            "2. ¿La respuesta esperada es determinista e inequívoca?\n"
            "3. ¿El razonamiento paso a paso es correcto?\n"
            f"4. ¿La dificultad es adecuada para nivel {nivel}?\n\n"
            "Veredicto: APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA."
        )
        out_rev = (
            "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) "
            "seguido de un comentario detallado."
        )

    else:  # ABIERTA
        desc_gen = (
            f"Contexto: pregunta abierta para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}'. "
            "Formula UNA pregunta abierta corta que requiera al estudiante razonar "
            "sobre el código: explicar una decisión de diseño, describir el propósito "
            "de un bloque concreto, identificar una limitación, o proponer cómo "
            "extenderlo para un nuevo requisito. Incluye una respuesta modelo orientativa."
            f"{codigo_bloque}"
        )
        out_gen = (
            "Pregunta abierta con enunciado claro y una respuesta modelo orientativa "
            "que el docente puede usar como referencia para la corrección."
        )
        desc_rev = (
            f"Contexto: pregunta abierta para {desc}.\n\n"
            "Revisa la pregunta evaluando:\n"
            "1. ¿El enunciado está bien delimitado (no es demasiado vago)?\n"
            "2. ¿La respuesta modelo es técnicamente correcta?\n"
            "3. ¿La pregunta requiere comprensión real del código, no solo lectura "
            "superficial?\n"
            f"4. ¿La dificultad es adecuada para nivel {nivel}?\n\n"
            "Veredicto: APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA."
        )
        out_rev = (
            "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) "
            "seguido de un comentario detallado."
        )

    return desc_gen, out_gen, desc_rev, out_rev


def construir_crew_para_unidad(
    unidad: UnidadCodigo,
    contexto: ContextoAcademico,
    tipo_pregunta: TipoPregunta = TipoPregunta.TEST,
) -> Crew:
    """Crea un crew con las tareas de generar + revisar para una unidad."""
    tipo_str = "función" if unidad.tipo == "funcion" else "clase"
    docstring_info = f"\nDocstring: {unidad.docstring}" if unidad.docstring else ""
    desc = contexto.descripcion()

    desc_gen, out_gen, desc_rev, out_rev = _prompts_por_tipo(
        tipo_pregunta, unidad, tipo_str, docstring_info, desc, contexto.nivel
    )

    agente_generador = Agent(
        role="Docente generador de preguntas",
        goal="Crear una pregunta de examen clara y bien formulada sobre un fragmento de código.",
        backstory=(
            f"Eres un profesor con años de experiencia diseñando exámenes para "
            f"{contexto.asignatura} de {contexto.titulacion}. Tus preguntas están "
            f"calibradas para estudiantes de {contexto.curso} con nivel {contexto.nivel}: "
            "ni triviales ni esotéricas. Evalúan comprensión real del código."
        ),
        llm=llm_haiku,
        verbose=True,
    )

    agente_revisor = Agent(
        role="Revisor pedagógico de preguntas de examen",
        goal="Validar que las preguntas son claras, técnicamente correctas y adecuadas al nivel.",
        backstory=(
            "Eres un coordinador docente experto en evaluación. Detectas errores "
            "técnicos, ambigüedades y preguntas triviales, y devuelves un veredicto "
            "claro con sugerencias concretas cuando es necesario."
        ),
        llm=llm_haiku,
        verbose=True,
    )

    tarea_generar = Task(
        description=desc_gen,
        expected_output=out_gen,
        agent=agente_generador,
    )

    tarea_revisar = Task(
        description=desc_rev,
        expected_output=out_rev,
        agent=agente_revisor,
        context=[tarea_generar],
    )

    return Crew(
        agents=[agente_generador, agente_revisor],
        tasks=[tarea_generar, tarea_revisar],
        process=Process.sequential,
        verbose=True,
    )


# ------------------------- Pipeline principal -------------------------

def procesar_archivo(
    ruta_archivo: str | Path,
    contexto: ContextoAcademico | None = None,
) -> list[dict]:
    """Procesa un archivo: extrae unidades, filtra triviales y genera+revisa preguntas."""
    if contexto is None:
        contexto = ContextoAcademico()

    unidades = extraer_unidades(ruta_archivo)

    triviales = [u for u in unidades if u.es_trivial()]
    a_procesar = [u for u in unidades if not u.es_trivial()]

    print(f"\n{'#' * 60}")
    print(f"# Encontradas {len(unidades)} unidades en {ruta_archivo}")
    print(f"# Contexto: {contexto.descripcion()}")
    if triviales:
        print(f"# Descartadas {len(triviales)} triviales: {[u.nombre for u in triviales]}")
    print(f"# A procesar: {len(a_procesar)}")
    print(f"{'#' * 60}\n")

    tipos = contexto.tipos_pregunta
    resultados: list[dict] = []
    for i, unidad in enumerate(a_procesar, start=1):
        tipo = tipos[(i - 1) % len(tipos)]
        print(f"\n{'=' * 60}")
        print(f"UNIDAD {i}/{len(a_procesar)}: {unidad}  [tipo: {tipo.value}]")
        print(f"{'=' * 60}")
        crew = construir_crew_para_unidad(unidad, contexto, tipo)
        salida = crew.kickoff()
        resultados.append({"unidad": unidad, "tipo": tipo, "salida": salida})

    return resultados


# Directorios que no contienen código del alumno
_DIRS_IGNORADOS = {
    ".venv", "venv", "__pycache__", ".git",
    "node_modules", "dist", "build", "migrations",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


def procesar_repositorio(
    ruta_carpeta: str | Path,
    contexto: ContextoAcademico | None = None,
) -> list[dict]:
    """Procesa todos los archivos soportados de una carpeta recursivamente."""
    if contexto is None:
        contexto = ContextoAcademico()

    carpeta = Path(ruta_carpeta)
    extensiones = set(lenguajes_soportados())

    archivos = [
        p for p in carpeta.rglob("*")
        if p.is_file()
        and p.suffix in extensiones
        and not any(parte in _DIRS_IGNORADOS for parte in p.parts)
    ]

    print(f"\n{'#' * 60}")
    print(f"# Repositorio: {carpeta}")
    print(f"# Archivos encontrados: {len(archivos)}")
    print(f"# Contexto: {contexto.descripcion()}")
    print(f"{'#' * 60}\n")

    todos: list[dict] = []
    for archivo in sorted(archivos):
        todos.extend(procesar_archivo(archivo, contexto))

    return todos


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: uv run python src/generador/pipeline_repositorio.py <archivo_o_carpeta>")
        sys.exit(1)

    ruta = Path(sys.argv[1])
    # Contexto de ejemplo — en la versión web el docente lo configurará
    contexto = ContextoAcademico(
        asignatura="Estructuras de Datos",
        curso="2º de Grado",
        titulacion="Ingeniería Informática",
        nivel="intermedio",
        tipos_pregunta=[TipoPregunta.TEST, TipoPregunta.TRAZA, TipoPregunta.ABIERTA],
    )

    if ruta.is_dir():
        resultados = procesar_repositorio(ruta, contexto)
    else:
        resultados = procesar_archivo(ruta, contexto)

    print(f"\n{'#' * 60}")
    print(f"# RESUMEN: {len(resultados)} preguntas generadas")
    print(f"{'#' * 60}\n")
    for i, r in enumerate(resultados, start=1):
        print(f"\n--- Pregunta {i} [{r['tipo'].value}]: {r['unidad']} ---\n")
        print(r["salida"])
