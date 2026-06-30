"""Selección determinista del corpus para el estudio de ablación (sin LLM).

Recorre los proyectos de origen, extrae sus unidades con el parser del sistema,
descarta triviales / demasiado grandes / duplicadas, y selecciona una muestra
estratificada por dificultad (nº de ramas). El resultado se guarda en
``corpus.json`` para inspeccionarlo antes de lanzar la generación.

Determinista: no usa azar; ordena por (nº ramas desc, nombre) y reparte cupos
fijos por estrato. Misma entrada -> misma salida.
"""

import json
import sys
from pathlib import Path

SRC = Path(r"c:/Users/Damian/Documents/UA_INFORMATICA/tfg/tfg-generador-examenes/src/generador")
sys.path.insert(0, str(SRC))

from parser import extraer_unidades, UnidadCodigo  # noqa: E402

_DIRS_IGNORADOS = {
    ".venv", "venv", "__pycache__", ".git", "node_modules",
    "dist", "build", "migrations", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

MAX_LINEAS = 80  # por encima de esto, la unidad es demasiado grande para una pregunta enfocada

# (nombre, ruta, lenguaje, cupo de unidades a seleccionar)
PROYECTOS = [
    ("SI-P1 (busqueda heuristica)",
     r"C:/Users/Damian/Documents/UA_INFORMATICA/3º/SI/SI-P1-ENTREGAFINAL/Fuente",
     "python", 14),
    ("Taxis Release 2 (SD)",
     r"C:/Users/Damian/Documents/UA_INFORMATICA/3º/SD/pracs/SD/Release 2",
     "python", 22),
    ("Prog3 (POO Java)",
     r"C:/Users/Damian/Documents/UA_INFORMATICA/2º/prog3/pracs",
     "java", 20),
]

# Patrón de archivos por lenguaje
_GLOB = {"python": "*.py", "java": "*.java"}


def es_archivo_test(p: Path) -> bool:
    """Excluye andamiaje de pruebas (JUnit/pytest), que no es lógica a evaluar."""
    posix = p.as_posix()
    return "/test/" in posix or p.name.endswith("Test.java") or p.name.startswith("test_")

# Reparto del cupo por estrato de dificultad (favorece las unidades con más lógica)
PROPORCION_ESTRATOS = {"alta": 0.40, "media": 0.35, "baja": 0.25}


def lineas(u: UnidadCodigo) -> int:
    return u.linea_fin - u.linea_inicio + 1


def estrato(u: UnidadCodigo) -> str:
    if u.num_ramas >= 6:
        return "alta"
    if u.num_ramas >= 3:
        return "media"
    return "baja"


def unidades_candidatas(raiz: Path, lenguaje: str):
    """Extrae unidades no triviales, dedup por nombre cualificado (la mejor copia)."""
    archivos = [
        p for p in raiz.rglob(_GLOB[lenguaje])
        if p.is_file()
        and not any(parte in _DIRS_IGNORADOS for parte in p.parts)
        and not es_archivo_test(p)
    ]
    mejor: dict[str, tuple[Path, UnidadCodigo]] = {}
    for arch in archivos:
        try:
            for u in extraer_unidades(arch):
                if u.es_trivial() or lineas(u) > MAX_LINEAS:
                    continue
                # dedup: ante copias del mismo nombre (lib/ replicado), quedarse
                # con la de más ramas (la versión más completa)
                prev = mejor.get(u.nombre)
                if prev is None or u.num_ramas > prev[1].num_ramas:
                    mejor[u.nombre] = (arch, u)
        except Exception as e:
            print(f"  [ERROR] {arch.name}: {e}")
    return list(mejor.values())


def seleccionar(candidatas, cupo):
    """Selección estratificada determinista."""
    por_estrato = {"alta": [], "media": [], "baja": []}
    for arch, u in candidatas:
        por_estrato[estrato(u)].append((arch, u))
    for lista in por_estrato.values():
        lista.sort(key=lambda x: (-x[1].num_ramas, x[1].nombre))

    seleccion = []
    for nivel, prop in PROPORCION_ESTRATOS.items():
        n = round(cupo * prop)
        seleccion.extend(por_estrato[nivel][:n])
    # Si por redondeo falta o sobra, ajustar con lo que haya
    if len(seleccion) < cupo:
        restantes = [x for x in candidatas if x not in seleccion]
        restantes.sort(key=lambda x: (-x[1].num_ramas, x[1].nombre))
        seleccion.extend(restantes[:cupo - len(seleccion)])
    return seleccion[:cupo]


def main():
    corpus = []
    raiz_repo = Path(SRC).parent.parent  # .../tfg-generador-examenes
    for nombre_proy, ruta, lenguaje, cupo in PROYECTOS:
        cands = unidades_candidatas(Path(ruta), lenguaje)
        sel = seleccionar(cands, cupo)
        print(f"\n{'=' * 70}\n{nombre_proy}\n{'=' * 70}")
        print(f"Candidatas: {len(cands)} | seleccionadas: {len(sel)}")
        cuenta = {"alta": 0, "media": 0, "baja": 0}
        for arch, u in sel:
            cuenta[estrato(u)] += 1
            corpus.append({
                "proyecto": nombre_proy,
                "lenguaje": lenguaje,
                "archivo": str(arch),
                "nombre": u.nombre,
                "tipo": u.tipo,
                "num_ramas": u.num_ramas,
                "lineas": lineas(u),
                "docstring": u.docstring,
                "codigo": u.codigo,
            })
            print(f"  - {u.nombre:42s} {u.tipo:8s} ramas={u.num_ramas:2d} lineas={lineas(u):3d}")
        print(f"  Estratos: {cuenta}")

    salida = raiz_repo / "ablacion" / "corpus.json"
    salida.write_text(json.dumps(corpus, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n>>> {len(corpus)} unidades guardadas en {salida}")


if __name__ == "__main__":
    main()
