"""Pipeline que procesa un archivo Python completo.

Combina el parser AST con el patrón generator-critic: por cada función
o clase extraída del archivo, genera una pregunta tipo test y la revisa
con un segundo agente, devolviendo el conjunto de preguntas resultantes.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Permitir importar otros módulos del mismo directorio cuando se ejecuta
# como script directo (`uv run python src/generador/pipeline_repositorio.py`).
sys.path.insert(0, str(Path(__file__).parent))

from crewai import Agent, Crew, LLM, Process, Task

from parser import UnidadCodigo, extraer_unidades

llm_haiku = LLM(
    model="bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0",
)


# ------------------------- Agentes -------------------------

generador = Agent(
    role="Docente generador de preguntas",
    goal=(
        "Crear una pregunta tipo test clara y bien formulada sobre un "
        "fragmento de código Python."
    ),
    backstory=(
        "Eres un profesor de programación con años de experiencia diseñando "
        "exámenes para estudiantes de Ingeniería Informática. Tus preguntas "
        "son precisas, evalúan comprensión real del código y tienen un único "
        "distractor obviamente incorrecto, dos plausibles pero incorrectos, "
        "y una respuesta correcta inequívoca."
    ),
    llm=llm_haiku,
    verbose=True,
)

revisor = Agent(
    role="Revisor pedagógico de preguntas de examen",
    goal=(
        "Validar que las preguntas generadas son claras, técnicamente "
        "correctas y pedagógicamente útiles."
    ),
    backstory=(
        "Eres un coordinador docente con experiencia en evaluación. Tu papel "
        "es ser un crítico constructivo: detectas problemas que el generador "
        "pueda haber pasado por alto y devuelves un veredicto claro junto "
        "con sugerencias concretas de mejora cuando sea necesario."
    ),
    llm=llm_haiku,
    verbose=True,
)


# ------------------------- Tareas por unidad -------------------------

def construir_crew_para_unidad(unidad: UnidadCodigo) -> Crew:
    """Crea un crew con las tareas de generar + revisar para una unidad."""
    contexto_tipo = "función" if unidad.tipo == "funcion" else "clase"
    docstring_info = (
        f"\nDocstring: {unidad.docstring}" if unidad.docstring else ""
    )

    tarea_generar = Task(
        description=(
            f"Analiza la siguiente {contexto_tipo} Python llamada "
            f"'{unidad.nombre}' y genera UNA pregunta tipo test con 4 "
            "opciones (A, B, C, D), donde solo una es correcta. La "
            "pregunta debe evaluar comprensión del comportamiento del "
            "código, no sintaxis trivial. Indica al final cuál es la "
            "respuesta correcta y justifica brevemente por qué."
            f"{docstring_info}\n\n"
            f"Código:\n```python\n{unidad.codigo}\n```"
        ),
        expected_output=(
            "Una pregunta tipo test con enunciado claro, 4 opciones "
            "etiquetadas A-D, la respuesta correcta indicada y una "
            "justificación breve."
        ),
        agent=generador,
    )

    tarea_revisar = Task(
        description=(
            "Revisa la pregunta generada por el agente anterior. Evalúala "
            "según estos criterios:\n"
            "1. ¿El enunciado es claro y preciso?\n"
            "2. ¿Las 4 opciones están bien planteadas (una correcta "
            "inequívoca, distractores plausibles)?\n"
            "3. ¿La respuesta marcada como correcta lo es realmente, dado "
            "el código original?\n"
            "4. ¿La justificación que da el generador es correcta?\n"
            "5. ¿El nivel de dificultad es apropiado para un estudiante "
            "de Ingeniería Informática?\n\n"
            "Devuelve un veredicto en una de estas tres categorías: "
            "APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA, seguido de "
            "un comentario justificando el veredicto."
        ),
        expected_output=(
            "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) "
            "seguido de un comentario detallado justificando la decisión."
        ),
        agent=revisor,
        context=[tarea_generar],
    )

    return Crew(
        agents=[generador, revisor],
        tasks=[tarea_generar, tarea_revisar],
        process=Process.sequential,
        verbose=True,
    )


# ------------------------- Pipeline principal -------------------------

def procesar_archivo(ruta_archivo: str | Path) -> list[dict]:
    """Procesa un archivo .py: extrae unidades y genera+revisa preguntas."""
    unidades = extraer_unidades(ruta_archivo)
    print(f"\n{'#' * 60}")
    print(f"# Encontradas {len(unidades)} unidades en {ruta_archivo}")
    print(f"{'#' * 60}\n")

    resultados: list[dict] = []
    for i, unidad in enumerate(unidades, start=1):
        print(f"\n{'=' * 60}")
        print(f"UNIDAD {i}/{len(unidades)}: {unidad}")
        print(f"{'=' * 60}")
        crew = construir_crew_para_unidad(unidad)
        salida = crew.kickoff()
        resultados.append({"unidad": unidad, "salida": salida})

    return resultados


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: uv run python src/generador/pipeline_repositorio.py <archivo.py>")
        sys.exit(1)

    ruta = sys.argv[1]
    resultados = procesar_archivo(ruta)

    print(f"\n{'#' * 60}")
    print(f"# RESUMEN: {len(resultados)} preguntas generadas")
    print(f"{'#' * 60}\n")
    for i, r in enumerate(resultados, start=1):
        print(f"\n--- Pregunta {i}: {r['unidad']} ---\n")
        print(r["salida"])
