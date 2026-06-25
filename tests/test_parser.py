"""Tests del análisis de código y del filtrado de unidades triviales."""

from pathlib import Path

import pytest

from generador import extraer_unidades, lenguajes_soportados, UnidadCodigo

EJEMPLO = Path(__file__).parent.parent / "ejemplos" / "ejemplo_simple.py"


# ------------------------- Extracción de unidades -------------------------

def test_extrae_todas_las_unidades():
    nombres = {u.nombre for u in extraer_unidades(EJEMPLO)}
    assert nombres == {"saludar", "factorial", "es_primo", "Pila"}


def test_distingue_funciones_de_clases():
    unidades = {u.nombre: u for u in extraer_unidades(EJEMPLO)}
    assert unidades["factorial"].tipo == "funcion"
    assert unidades["Pila"].tipo == "clase"


def test_extrae_docstring():
    unidades = {u.nombre: u for u in extraer_unidades(EJEMPLO)}
    assert unidades["factorial"].docstring is not None
    assert "factorial" in unidades["factorial"].docstring.lower()


def test_cuenta_estructuras_de_control():
    unidades = {u.nombre: u for u in extraer_unidades(EJEMPLO)}
    # es_primo tiene dos 'if' y un 'for'
    assert unidades["es_primo"].num_ramas >= 3
    # saludar no contiene ninguna estructura de control
    assert unidades["saludar"].num_ramas == 0


def test_extension_no_soportada():
    with pytest.raises(ValueError):
        extraer_unidades("archivo.txt")


def test_lenguajes_soportados_incluye_python():
    assert ".py" in lenguajes_soportados()


# ------------------------- Filtrado de triviales -------------------------

def _unidad(num_ramas: int, lineas: int) -> UnidadCodigo:
    return UnidadCodigo(
        tipo="funcion", nombre="f", codigo="", docstring=None,
        linea_inicio=1, linea_fin=lineas, num_ramas=num_ramas,
    )


def test_trivial_si_es_corta_y_sin_ramas():
    assert _unidad(num_ramas=0, lineas=3).es_trivial() is True


def test_no_trivial_si_tiene_ramas():
    assert _unidad(num_ramas=1, lineas=3).es_trivial() is False


def test_no_trivial_si_es_larga():
    assert _unidad(num_ramas=0, lineas=10).es_trivial() is False


def test_filtrado_sobre_el_ejemplo():
    unidades = {u.nombre: u for u in extraer_unidades(EJEMPLO)}
    assert unidades["saludar"].es_trivial() is True
    assert unidades["factorial"].es_trivial() is False
    assert unidades["es_primo"].es_trivial() is False
