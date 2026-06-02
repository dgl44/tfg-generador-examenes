"""Pipeline CrewAI con dos agentes: generador + revisor (patrón generator-critic).

El generador propone una pregunta tipo test sobre un fragmento de código.
El revisor evalúa la calidad de la pregunta (claridad, corrección técnica,
plausibilidad de los distractores) y emite un veredicto.

Ambas tareas se ejecutan de forma secuencial; CrewAI pasa automáticamente el
output del generador como contexto a la tarea de revisión gracias al parámetro
`context=[tarea_generar]`.
"""

from dotenv import load_dotenv

load_dotenv()

from crewai import Agent, Crew, LLM, Process, Task

llm_haiku = LLM(
    model="bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0",
)

CODIGO_EJEMPLO = '''
def factorial(n):
    """Calcula el factorial de n de forma recursiva."""
    if n == 0:
        return 1
    return n * factorial(n - 1)
'''


# ------------------------- Agentes -------------------------

generador = Agent(
    role="Docente generador de preguntas",
    goal=(
        "Crear una pregunta tipo test clara y bien formulada sobre un fragmento "
        "de código Python."
    ),
    backstory=(
        "Eres un profesor de programación con años de experiencia diseñando "
        "exámenes para estudiantes de Ingeniería Informática. Tus preguntas son "
        "precisas, evalúan comprensión real del código y tienen un único "
        "distractor obviamente incorrecto, dos plausibles pero incorrectos, y "
        "una respuesta correcta inequívoca."
    ),
    llm=llm_haiku,
    verbose=True,
)

revisor = Agent(
    role="Revisor pedagógico de preguntas de examen",
    goal=(
        "Validar que las preguntas generadas son claras, técnicamente correctas "
        "y pedagógicamente útiles. Detectar opciones ambiguas, errores en la "
        "respuesta marcada como correcta o preguntas triviales/excesivamente "
        "difíciles."
    ),
    backstory=(
        "Eres un coordinador docente con experiencia en evaluación. Tu papel es "
        "ser un crítico constructivo: detectas problemas que el generador pueda "
        "haber pasado por alto y devuelves un veredicto claro junto con "
        "sugerencias concretas de mejora cuando sea necesario."
    ),
    llm=llm_haiku,
    verbose=True,
)


# ------------------------- Tareas -------------------------

tarea_generar = Task(
    description=(
        "Analiza el siguiente fragmento de código Python y genera UNA pregunta "
        "tipo test con 4 opciones (A, B, C, D), donde solo una es correcta. "
        "La pregunta debe evaluar comprensión del comportamiento del código, no "
        "sintaxis trivial. Indica al final cuál es la respuesta correcta y "
        "justifica brevemente por qué.\n\n"
        f"Código:\n```python\n{CODIGO_EJEMPLO}\n```"
    ),
    expected_output=(
        "Una pregunta tipo test con enunciado claro, 4 opciones etiquetadas "
        "A-D, la respuesta correcta indicada y una justificación breve."
    ),
    agent=generador,
)

tarea_revisar = Task(
    description=(
        "Revisa la pregunta generada por el agente anterior. Evalúala según "
        "estos criterios:\n"
        "1. ¿El enunciado es claro y preciso?\n"
        "2. ¿Las 4 opciones están bien planteadas (una correcta inequívoca, "
        "distractores plausibles)?\n"
        "3. ¿La respuesta marcada como correcta lo es realmente, dado el "
        "código original?\n"
        "4. ¿La justificación que da el generador es correcta?\n"
        "5. ¿El nivel de dificultad es apropiado para un estudiante de "
        "Ingeniería Informática (ni trivial ni esotérico)?\n\n"
        "Devuelve un veredicto en una de estas tres categorías: APROBADA, "
        "APROBADA CON SUGERENCIAS o RECHAZADA, seguido de un comentario "
        "justificando el veredicto y, si aplica, sugerencias concretas de "
        "mejora."
    ),
    expected_output=(
        "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) seguido "
        "de un comentario detallado justificando la decisión y, si procede, "
        "sugerencias de mejora."
    ),
    agent=revisor,
    context=[tarea_generar],
)


# ------------------------- Crew -------------------------

crew = Crew(
    agents=[generador, revisor],
    tasks=[tarea_generar, tarea_revisar],
    process=Process.sequential,
    verbose=True,
)


if __name__ == "__main__":
    resultado = crew.kickoff()
    print("\n" + "=" * 60)
    print("RESULTADO FINAL DEL CREW")
    print("=" * 60)
    print(resultado)
