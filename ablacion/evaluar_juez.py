"""Juez externo (LLM-as-judge) con Sonnet 4.6 para el estudio de ablación.

Por cada pregunta generada, recibe el código y el enunciado (NO el veredicto del
revisor) y emite una etiqueta binaria BUENA/DEFECTUOSA según una rúbrica. Es la
verdad de referencia independiente contra la que se mide al agente revisor.

- Guarda tras cada pregunta (reanudable).
- Uso: python ablacion/evaluar_juez.py [LIMITE]
"""

import json
import sys
import time
from pathlib import Path

import truststore  # noqa: E402
truststore.inject_into_ssl()

REPO = Path(r"c:/Users/Damian/Documents/UA_INFORMATICA/tfg/tfg-generador-examenes")

from dotenv import load_dotenv  # noqa: E402
load_dotenv(REPO / ".env")

from crewai import LLM  # noqa: E402

import os  # noqa: E402
_TAG = os.environ.get("ABLACION_TAG", "")
_SUF = f"_{_TAG}" if _TAG else ""
# Sufijo independiente para la SALIDA del juez (permite re-juzgar las mismas
# preguntas con otro prompt sin pisar la evaluación anterior).
_JUEZ = os.environ.get("JUEZ_TAG", "")
_JSUF = f"_{_JUEZ}" if _JUEZ else ""

RESULTADOS = REPO / "ablacion" / f"resultados_ablacion{_SUF}.json"
SALIDA = REPO / "ablacion" / f"evaluacion_juez{_SUF}{_JSUF}.json"

juez = LLM(model="bedrock/us.anthropic.claude-sonnet-4-6")

PROMPT = """\
Eres un docente experto en evaluación. Debes decidir si una pregunta de examen \
generada automáticamente a partir de un fragmento de código tiene algún defecto \
OBJETIVO que la inutilice, evaluando la comprensión del código de un estudiante \
de grado en informática.

Se te da el CÓDIGO y la PREGUNTA generada (que incluye su respuesta correcta y \
su justificación). No recibes ninguna valoración previa: juzga por ti mismo.

Marca DEFECTUOSA SOLO si se da al menos uno de estos defectos objetivos:
1. Incorrección técnica: la pregunta o la respuesta marcada como correcta es \
errónea respecto al código (la traza, el valor o la afirmación no cuadran).
2. Ambigüedad irresoluble: en tipo test, hay dos o más opciones igualmente \
correctas o ninguna correcta; en abierta, no existe una respuesta delimitada y \
verificable.
3. No verificable con el código: la respuesta depende de información que NO \
está en el código mostrado (se la inventa).

En CUALQUIER otro caso, marca BUENA. MUY IMPORTANTE: que una pregunta te parezca \
algo trivial, demasiado abierta, sencilla o "mejorable" NO la hace defectuosa; \
si es técnicamente correcta, inequívoca y verificable con el código, es BUENA. \
No apliques tu gusto sobre dificultad o estilo: solo defectos objetivos.

CÓDIGO:
```
{codigo}
```

PREGUNTA GENERADA:
{enunciado}

Responde EXACTAMENTE en este formato, sin nada más:
VEREDICTO: BUENA
MOTIVO: <una o dos frases, citando el defecto objetivo si lo hay>
"""


def etiqueta(texto: str) -> str:
    t = texto.upper()
    pos = t.rfind("VEREDICTO")
    ventana = t[pos:pos + 40] if pos != -1 else t
    if "DEFECTUOSA" in ventana:
        return "DEFECTUOSA"
    if "BUENA" in ventana:
        return "BUENA"
    # Respaldo: escanear todo el texto
    if "DEFECTUOSA" in t:
        return "DEFECTUOSA"
    if "BUENA" in t:
        return "BUENA"
    return "DESCONOCIDO"


def main():
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else None
    datos = [r for r in json.loads(RESULTADOS.read_text(encoding="utf-8")) if "error" not in r]
    if limite:
        datos = datos[:limite]

    hechos = {}
    if SALIDA.exists():
        for r in json.loads(SALIDA.read_text(encoding="utf-8")):
            if r.get("etiqueta_juez") not in (None, "DESCONOCIDO"):
                hechos[(r["proyecto"], r["nombre"])] = r
    salida = list(hechos.values())

    total = len(datos)
    for i, item in enumerate(datos, start=1):
        clave = (item["proyecto"], item["nombre"])
        if clave in hechos:
            print(f"[{i}/{total}] (omitida) {item['nombre']}")
            continue

        print(f"[{i}/{total}] {item['nombre']}  [{item['tipo_pregunta']}]")
        prompt = PROMPT.format(codigo=item["codigo"], enunciado=item["pregunta_generada"])
        t0 = time.time()
        try:
            respuesta = juez.call(prompt)
            lab = etiqueta(respuesta)
            reg = {
                "proyecto": item["proyecto"],
                "lenguaje": item["lenguaje"],
                "nombre": item["nombre"],
                "tipo_pregunta": item["tipo_pregunta"],
                "num_ramas": item["num_ramas"],
                "veredicto_revisor": item["veredicto"],
                "etiqueta_juez": lab,
                "motivo_juez": respuesta.strip(),
                "segundos": round(time.time() - t0, 1),
            }
            print(f"      -> {lab}  ({reg['segundos']}s)")
        except Exception as e:
            reg = {**{k: item[k] for k in ("proyecto", "lenguaje", "nombre", "tipo_pregunta")},
                   "etiqueta_juez": "DESCONOCIDO", "error": str(e)}
            print(f"      -> ERROR: {e}")

        salida.append(reg)
        SALIDA.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n>>> {len(salida)} evaluadas. Guardado en {SALIDA}")


if __name__ == "__main__":
    main()
