"""Prepara una muestra ciega para validar el juez automático contra un humano.

Selecciona 15 preguntas (mezcla Python/Java y casos buenos/defectuosos según el
juez, SIN mostrar esas etiquetas), genera:
  - validacion_muestra.md      -> para leer y valorar cada pregunta
  - mis_respuestas.txt         -> plantilla donde Damián escribe BUENA/DEFECTUOSA
  - validacion_clave.json      -> clave oculta (juez + revisor) para comparar luego
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVAL = REPO / "ablacion" / "evaluacion_juez_v2.json"
RESULTADOS = REPO / "ablacion" / "resultados_ablacion_v2.json"

PLAN = [("python", "BUENA", 4), ("python", "DEFECTUOSA", 4),
        ("java", "BUENA", 3), ("java", "DEFECTUOSA", 4)]

RUBRICA = """\
Una pregunta es BUENA solo si cumple TODOS estos criterios (si falla uno, DEFECTUOSA):
1. Correcta técnicamente: la pregunta y su respuesta marcada como correcta son
   correctas respecto al código.
2. Relevante: evalúa algo significativo del código, no un detalle irrelevante.
3. Nivel adecuado: ni trivial ni imposible para un estudiante de grado.
4. Bien formulada: enunciado claro y sin ambigüedades; si es tipo test, solo una
   opción es correcta y los distractores son razonables.
"""


def main():
    ev = [r for r in json.loads(EVAL.read_text(encoding="utf-8"))
          if r.get("etiqueta_juez") in ("BUENA", "DEFECTUOSA")]

    # El código y el enunciado están en los resultados; se unen por (proyecto, nombre).
    res = {(r["proyecto"], r["nombre"]): r
           for r in json.loads(RESULTADOS.read_text(encoding="utf-8")) if "error" not in r}
    for r in ev:
        full = res.get((r["proyecto"], r["nombre"]), {})
        r["codigo"] = full.get("codigo", "")
        r["pregunta_generada"] = full.get("pregunta_generada", "")

    seleccion = []
    for lenguaje, etiqueta, n in PLAN:
        cands = sorted([r for r in ev if r["lenguaje"] == lenguaje
                        and r["etiqueta_juez"] == etiqueta],
                       key=lambda r: r["nombre"])
        seleccion.extend(cands[:n])

    # Orden de presentación determinista que mezcla lenguajes/etiquetas.
    seleccion.sort(key=lambda r: r["nombre"])

    md = ["# Validación ciega del juez\n",
          "Valora cada pregunta como **BUENA** o **DEFECTUOSA** según esta rúbrica. "
          "Apunta tu respuesta en `mis_respuestas.txt`.\n",
          f"```\n{RUBRICA}```\n", "---\n"]
    clave = []
    plantilla = []
    for i, r in enumerate(seleccion, start=1):
        md.append(f"## Pregunta {i:02d}  (lenguaje: {r['lenguaje']})\n")
        md.append(f"**Código — `{r['nombre']}`:**\n")
        md.append(f"```\n{r['codigo']}\n```\n")
        md.append("**Pregunta generada:**\n")
        md.append(f"{r['pregunta_generada']}\n")
        md.append(f"\n> Tu valoración (BUENA / DEFECTUOSA): _____________\n\n---\n")
        plantilla.append(f"{i:02d}=")
        clave.append({"n": i, "nombre": r["nombre"], "lenguaje": r["lenguaje"],
                      "etiqueta_juez": r["etiqueta_juez"],
                      "veredicto_revisor": r["veredicto_revisor"]})

    (REPO / "ablacion" / "validacion_muestra.md").write_text("\n".join(md), encoding="utf-8")
    (REPO / "ablacion" / "mis_respuestas.txt").write_text(
        "# Escribe BUENA o DEFECTUOSA tras cada =\n" + "\n".join(plantilla) + "\n",
        encoding="utf-8")
    (REPO / "ablacion" / "validacion_clave.json").write_text(
        json.dumps(clave, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Muestra de {len(seleccion)} preguntas generada:")
    print(f"  - Lee:      ablacion/validacion_muestra.md")
    print(f"  - Responde: ablacion/mis_respuestas.txt")
    from collections import Counter
    print("  Composición:", dict(Counter((r['lenguaje'], r['etiqueta_juez']) for r in seleccion)))


if __name__ == "__main__":
    main()
