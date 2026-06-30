"""Recalcula el acuerdo humano-juez usando un fichero de juez alternativo.

Reutiliza las MISMAS 15 preguntas (validacion_clave.json) y las respuestas ya
dadas por Damián (mis_respuestas.txt), pero toma las etiquetas del juez del
fichero indicado por JUEZ_FILE (por defecto, el juez objetivo).
"""

import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAVE = REPO / "ablacion" / "validacion_clave.json"
RESP = REPO / "ablacion" / "mis_respuestas.txt"
JUEZ = REPO / "ablacion" / os.environ.get("JUEZ_FILE", "evaluacion_juez_v2_obj.json")


def normaliza(v: str) -> str:
    v = v.strip().upper()
    return "BUENA" if v.startswith("B") else "DEFECTUOSA" if v.startswith("D") else ""


def main():
    clave = json.loads(CLAVE.read_text(encoding="utf-8"))
    juez = {r["nombre"]: r["etiqueta_juez"]
            for r in json.loads(JUEZ.read_text(encoding="utf-8"))}
    humanas = {}
    for linea in RESP.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\d+)\s*=\s*(\w+)", linea)
        if m and normaliza(m.group(2)):
            humanas[int(m.group(1))] = normaliza(m.group(2))

    pares = []
    for c in clave:
        n = c["n"]
        if n in humanas and c["nombre"] in juez:
            pares.append((n, c, humanas[n], juez[c["nombre"]]))

    N = len(pares)
    acuerdos = sum(1 for _, _, h, j in pares if h == j)
    po = acuerdos / N
    pe = sum((sum(1 for _, _, h, _ in pares if h == L) / N) *
             (sum(1 for _, _, _, j in pares if j == L) / N)
             for L in ("BUENA", "DEFECTUOSA"))
    kappa = (po - pe) / (1 - pe) if pe != 1 else 1.0
    nivel = ('casi perfecto' if kappa >= .81 else 'sustancial' if kappa >= .61
             else 'moderado' if kappa >= .41 else 'aceptable' if kappa >= .21 else 'débil')

    print(f"Juez: {JUEZ.name}")
    print(f"Acuerdo humano-juez: {acuerdos}/{N} = {100*po:.0f}%")
    print(f"Kappa de Cohen: {kappa:.2f}  ({nivel})")
    desac = [(n, c, h, j) for n, c, h, j in pares if h != j]
    if desac:
        print("\nDesacuerdos restantes:")
        for n, c, h, j in desac:
            print(f"  P{n:02d} ({c['lenguaje']}, {c['nombre']}): humano={h} vs juez={j}")
    else:
        print("\nSin desacuerdos.")


if __name__ == "__main__":
    main()
