"""Prepara una muestra contextualizada de ~10 preguntas para que el TUTOR
(docente) las valore como ancla humana de la evaluación.

Genera:
  - muestra_tutor.md     -> documento limpio para enviar (contexto + rúbrica + preguntas)
  - respuestas_tutor.txt -> plantilla de respuestas
  - clave_tutor.json     -> clave oculta (etiqueta del juez) para comparar después
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTADOS = REPO / "ablacion" / "resultados_ablacion_v2.json"
JUEZ = REPO / "ablacion" / "evaluacion_juez_v2_obj.json"

# Cuántas preguntas tomar de cada proyecto
CUPOS = {
    "SI-P1 (busqueda heuristica)": 5,
    "Taxis Release 2 (SD)": 3,
    "Prog3 (POO Java)": 3,
}

CONTEXTO_PROYECTOS = """\
El código del que parten las preguntas son prácticas reales mías de la carrera:

- **Programación 3 (Java)**: prácticas de programación orientada a objetos
  (clases, herencia, interfaces, patrones de diseño).
- **Sistemas Inteligentes (Python)**: práctica de búsqueda heurística
  (implementación de A* y A*epsilon sobre un mapa).
- **Sistemas Distribuidos (Python)**: sistema de taxis que se comunican en
  tiempo real mediante sockets y Kafka (una central, taxis y clientes).
"""

RUBRICA = """\
Por favor, marca cada pregunta como **BUENA** o **DEFECTUOSA**. El criterio que
te pido (céntrate en defectos objetivos, no en si es mejorable de estilo):

- **DEFECTUOSA** si: es técnicamente incorrecta (la respuesta marcada no cuadra
  con el código), es ambigua (en test, varias o ninguna opción correcta), o su
  respuesta no se puede verificar con el código mostrado.
- **BUENA** en cualquier otro caso (aunque te parezca sencilla o mejorable).

Si quieres, añade una nota breve en las que marques defectuosa. ¡Gracias!
"""

NOMBRE_LEGIBLE = {
    "SI-P1 (busqueda heuristica)": "Sistemas Inteligentes (Python)",
    "Taxis Release 2 (SD)": "Sistemas Distribuidos (Python)",
    "Prog3 (POO Java)": "Programación 3 (Java)",
}


def seleccionar(resultados, juez):
    """Selección determinista: cupo por proyecto, asegurando algunas preguntas
    que el juez marcó DEFECTUOSA (para poder medir el acuerdo en casos malos) y
    diversificando el tipo de pregunta."""
    seleccion = []
    for proyecto, cupo in CUPOS.items():
        items = sorted([r for r in resultados if r["proyecto"] == proyecto],
                       key=lambda r: r["nombre"])
        elegidos = []
        # 1) Incluir hasta 2 defectuosas (si las hay) para tener casos discriminantes
        for r in [x for x in items if juez.get(x["nombre"]) == "DEFECTUOSA"][:2]:
            if len(elegidos) < cupo:
                elegidos.append(r)
        # 2) Diversificar tipo de pregunta con el resto
        tipos_vistos = [e["tipo_pregunta"] for e in elegidos]
        for r in items:
            if len(elegidos) >= cupo:
                break
            if r not in elegidos and r["tipo_pregunta"] not in tipos_vistos:
                elegidos.append(r)
                tipos_vistos.append(r["tipo_pregunta"])
        # 3) Completar cupo
        for r in items:
            if len(elegidos) >= cupo:
                break
            if r not in elegidos:
                elegidos.append(r)
        seleccion.extend(elegidos)
    return seleccion


def main():
    resultados = [r for r in json.loads(RESULTADOS.read_text(encoding="utf-8"))
                  if "error" not in r]
    juez = {r["nombre"]: r["etiqueta_juez"]
            for r in json.loads(JUEZ.read_text(encoding="utf-8"))}

    seleccion = seleccionar(resultados, juez)

    md = ["# Validación de preguntas generadas — TFG\n",
          "Hola Fidel. Te paso una muestra de preguntas que ha generado la "
          "herramienta sobre código de prácticas mías, para que me des tu criterio "
          "de docente sobre su calidad.\n",
          "## De dónde sale el código\n", CONTEXTO_PROYECTOS, "\n## Qué te pido\n", RUBRICA,
          "\n---\n"]
    clave, plantilla = [], []
    for i, r in enumerate(seleccion, start=1):
        md.append(f"## Pregunta {i:02d}\n")
        md.append(f"*Procedencia: {NOMBRE_LEGIBLE[r['proyecto']]} — `{r['nombre']}`*\n")
        md.append("**Código:**\n")
        md.append(f"```\n{r['codigo']}\n```\n")
        md.append("**Pregunta generada:**\n")
        md.append(f"{r['pregunta_generada']}\n")
        md.append("\n> **Tu valoración (BUENA / DEFECTUOSA):** ____________\n")
        md.append("> Nota (opcional): \n\n---\n")
        plantilla.append(f"{i:02d}=")
        clave.append({"n": i, "nombre": r["nombre"], "proyecto": r["proyecto"],
                      "lenguaje": r["lenguaje"], "tipo_pregunta": r["tipo_pregunta"],
                      "etiqueta_juez": juez.get(r["nombre"], "?")})

    (REPO / "ablacion" / "muestra_tutor.md").write_text("\n".join(md), encoding="utf-8")
    (REPO / "ablacion" / "respuestas_tutor.txt").write_text(
        "# El tutor escribe BUENA o DEFECTUOSA tras cada =\n" + "\n".join(plantilla) + "\n",
        encoding="utf-8")
    (REPO / "ablacion" / "clave_tutor.json").write_text(
        json.dumps(clave, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    print(f"Muestra de {len(seleccion)} preguntas para el tutor generada.")
    print("Por proyecto:", dict(Counter(r["proyecto"] for r in seleccion)))
    print("Por tipo:", dict(Counter(r["tipo_pregunta"] for r in seleccion)))
    print("Etiqueta juez (oculta):", dict(Counter(c["etiqueta_juez"] for c in clave)))


if __name__ == "__main__":
    main()
