"""Runner del estudio de ablación: genera (y revisa) una pregunta por unidad.

Carga ``corpus.json``, y por cada unidad ejecuta el crew generador+revisor
(Haiku, usar_revisor=True), guardando enunciado + veredicto + comentario en
``resultados_ablacion.json``. Una sola corrida con revisor da los dos brazos:
"sin revisor" = todas las preguntas; "con revisor" = solo las aprobadas.

- Guarda tras cada unidad (reanudable: omite las ya hechas).
- Reparte los 3 tipos de pregunta en round-robin.
- Uso: python ablacion/correr_ablacion.py [LIMITE]   (LIMITE opcional, para pruebas)
"""

import json
import sys
import time
from pathlib import Path

# Usar el almacén de certificados de Windows para el TLS de Python (boto3/crewai).
# Necesario tras interceptores TLS locales (antivirus/proxy) que certifi no conoce.
import truststore  # noqa: E402
truststore.inject_into_ssl()

REPO = Path(r"c:/Users/Damian/Documents/UA_INFORMATICA/tfg/tfg-generador-examenes")
sys.path.insert(0, str(REPO / "src" / "generador"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(REPO / ".env")

from parser import UnidadCodigo  # noqa: E402
from modelos import ContextoAcademico, TipoPregunta  # noqa: E402
from agentes import construir_crew_para_unidad  # noqa: E402
from pipeline import _construir_resultado  # noqa: E402

import os  # noqa: E402
_TAG = os.environ.get("ABLACION_TAG", "")
_SUF = f"_{_TAG}" if _TAG else ""

CORPUS = REPO / "ablacion" / "corpus.json"
SALIDA = REPO / "ablacion" / f"resultados_ablacion{_SUF}.json"

# Mismo contexto académico para todas las unidades (la ablación aísla el revisor).
CONTEXTO = ContextoAcademico(
    asignatura="Programación",
    curso="Grado",
    titulacion="Ingeniería Informática",
    nivel="intermedio",
    usar_revisor=True,
)

TIPOS = [TipoPregunta.TEST, TipoPregunta.TRAZA, TipoPregunta.ABIERTA]


def unidad_desde_dict(d: dict) -> UnidadCodigo:
    return UnidadCodigo(
        tipo=d["tipo"],
        nombre=d["nombre"],
        codigo=d["codigo"],
        docstring=d.get("docstring"),
        linea_inicio=1,
        linea_fin=d.get("lineas", 1),
        num_ramas=d.get("num_ramas", 0),
    )


def main():
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else None
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    if limite:
        corpus = corpus[:limite]

    # Reanudable: solo se omiten las unidades que terminaron BIEN (con veredicto);
    # las que fallaron se reintentan.
    hechos = {}
    if SALIDA.exists():
        for r in json.loads(SALIDA.read_text(encoding="utf-8")):
            if "error" not in r:
                hechos[(r["proyecto"], r["nombre"])] = r
    resultados = list(hechos.values())

    total = len(corpus)
    for i, item in enumerate(corpus, start=1):
        clave = (item["proyecto"], item["nombre"])
        if clave in hechos:
            print(f"[{i}/{total}] (omitida, ya hecha) {item['nombre']}")
            continue

        tipo = TIPOS[(i - 1) % len(TIPOS)]
        print(f"[{i}/{total}] {item['nombre']}  [tipo: {tipo.value}, lenguaje: {item['lenguaje']}]")
        unidad = unidad_desde_dict(item)
        t0 = time.time()
        try:
            crew = construir_crew_para_unidad(unidad, CONTEXTO, tipo)
            salida = crew.kickoff()
            res = _construir_resultado(unidad, tipo, salida)
            registro = {
                "proyecto": item["proyecto"],
                "lenguaje": item["lenguaje"],
                "nombre": item["nombre"],
                "tipo_unidad": item["tipo"],
                "num_ramas": item["num_ramas"],
                "lineas": item["lineas"],
                "tipo_pregunta": tipo.value,
                "veredicto": res.veredicto.value,
                "pregunta_generada": res.pregunta_generada,
                "comentario_revisor": res.comentario_revisor,
                "codigo": item["codigo"],
                "segundos": round(time.time() - t0, 1),
            }
            print(f"      -> {res.veredicto.value}  ({registro['segundos']}s)")
        except Exception as e:
            registro = {
                "proyecto": item["proyecto"], "lenguaje": item["lenguaje"],
                "nombre": item["nombre"], "tipo_pregunta": tipo.value,
                "error": str(e),
            }
            print(f"      -> ERROR: {e}")

        resultados.append(registro)
        SALIDA.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")

    ok = [r for r in resultados if "error" not in r]
    print(f"\n>>> {len(ok)}/{len(resultados)} unidades procesadas. Guardado en {SALIDA}")
    if ok:
        from collections import Counter
        print("Veredictos:", dict(Counter(r["veredicto"] for r in ok)))


if __name__ == "__main__":
    main()
