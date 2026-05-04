"""Primer agente CrewAI: genera una pregunta tipo test a partir de un fragmento
de código Python. Sin revisor todavía — el objetivo es validar que el pipeline
CrewAI + Bedrock + Haiku 4.5 funciona end-to-end.
"""

from dotenv import load_dotenv

load_dotenv()

from crewai import Agent, Crew, LLM, Task

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

tarea = Task(
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

crew = Crew(agents=[generador], tasks=[tarea], verbose=True)


if __name__ == "__main__":
    resultado = crew.kickoff()
    print("\n" + "=" * 60)
    print("RESULTADO FINAL")
    print("=" * 60)
    print(resultado)
