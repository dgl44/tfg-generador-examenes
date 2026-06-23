"""Generador automático de exámenes a partir de código fuente.

API pública del paquete. Permite al futuro frontend importar la funcionalidad
sin conocer la estructura interna de módulos::

    from generador import procesar_repositorio, ContextoAcademico, TipoPregunta

Las capas internas usan importaciones planas (from parser import ...); este
bootstrap añade el directorio del paquete a sys.path para que funcionen tanto
al importar el paquete como al ejecutar los módulos de forma directa.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modelos import (  # noqa: E402
    ContextoAcademico,
    ResultadoPregunta,
    TipoPregunta,
    Veredicto,
)
from parser import UnidadCodigo, extraer_unidades, lenguajes_soportados  # noqa: E402
from pipeline import procesar_archivo, procesar_repositorio  # noqa: E402

__all__ = [
    "ContextoAcademico",
    "TipoPregunta",
    "Veredicto",
    "ResultadoPregunta",
    "UnidadCodigo",
    "extraer_unidades",
    "lenguajes_soportados",
    "procesar_archivo",
    "procesar_repositorio",
]
