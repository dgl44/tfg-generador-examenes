"""Tests del análisis de código y del filtrado de unidades triviales."""

from pathlib import Path

import pytest

from generador import extraer_unidades, lenguajes_soportados, UnidadCodigo, firma_unidad

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


# ------------------------- Extracción de métodos -------------------------

def test_clase_pequena_se_extrae_entera():
    # Pila es una clase corta y cohesionada: se conserva como un todo.
    unidades = {u.nombre: u for u in extraer_unidades(EJEMPLO)}
    assert unidades["Pila"].tipo == "clase"
    assert not any("." in n for n in unidades)  # no se desglosa en métodos


_CLASE_GRANDE = '''\
class Servicio:
    """Una clase extensa que debe descomponerse en métodos."""

    def __init__(self, datos):
        self.datos = datos
        self.cache = {}
        self.activo = True

    def get_datos(self):
        return self.datos

    def procesar(self, entradas):
        resultado = []
        for x in entradas:
            if x > 0:
                resultado.append(x * 2)
            else:
                resultado.append(0)
        return resultado

    def validar(self, valor):
        if valor is None:
            return False
        if valor in self.cache:
            return True
        for clave in self.datos:
            if clave == valor:
                return True
        return False

    def resumen(self, items):
        total = 0
        for it in items:
            if it.activo:
                total += it.peso
            else:
                total -= it.peso
        return total

    def filtrar(self, items, umbral):
        seleccion = []
        for it in items:
            if it.valor >= umbral:
                seleccion.append(it)
        return seleccion
'''


def test_clase_grande_se_desglosa_en_metodos(tmp_path):
    archivo = tmp_path / "servicio.py"
    archivo.write_text(_CLASE_GRANDE, encoding="utf-8")
    nombres = {u.nombre: u for u in extraer_unidades(archivo)}

    # La clase grande NO aparece como unidad propia.
    assert "Servicio" not in nombres
    # Sus métodos con lógica sí, con el nombre cualificado por la clase.
    assert nombres["Servicio.procesar"].tipo == "metodo"
    assert nombres["Servicio.validar"].tipo == "metodo"
    # Los dunder se omiten.
    assert "Servicio.__init__" not in nombres


def test_metodo_dunder_excluido(tmp_path):
    archivo = tmp_path / "servicio.py"
    archivo.write_text(_CLASE_GRANDE, encoding="utf-8")
    assert all(not n.endswith(".__init__") for n in
               {u.nombre for u in extraer_unidades(archivo)})


# ------------------------- Backend de Java -------------------------

_CLASE_JAVA = """\
package es.ua.prog3;

/** Servicio de ejemplo con varios métodos. */
public class Servicio {

    private int[] datos;

    public Servicio(int[] datos) {
        this.datos = datos;
    }

    /** Suma los valores positivos. */
    public int sumarPositivos(int[] valores) {
        int total = 0;
        for (int v : valores) {
            if (v > 0) {
                total += v;
            }
        }
        return total;
    }

    public boolean contiene(int objetivo) {
        for (int d : datos) {
            if (d == objetivo) {
                return true;
            }
        }
        return false;
    }

    public int maximo() {
        int m = datos[0];
        for (int d : datos) {
            if (d > m) {
                m = d;
            }
        }
        return m;
    }

    public int minimo() {
        int m = datos[0];
        for (int d : datos) {
            if (d < m) {
                m = d;
            }
        }
        return m;
    }

    public double media() {
        int total = 0;
        for (int d : datos) {
            total += d;
        }
        return (double) total / datos.length;
    }
}
"""


def _u(nombre, codigo):
    return UnidadCodigo(tipo="funcion", nombre=nombre, codigo=codigo, docstring=None,
                        linea_inicio=1, linea_fin=2, num_ramas=0)


def test_firma_igual_para_codigo_identico():
    a = _u("f", "def f():\n    return 1")
    b = _u("f", "def f():\n    return 1")
    assert firma_unidad(a) == firma_unidad(b)


def test_firma_ignora_espacios_y_lineas_vacias():
    a = _u("f", "def f():\n    return 1")
    b = _u("f", "def f():\n\n    return 1   \n")
    assert firma_unidad(a) == firma_unidad(b)


def test_firma_distinta_si_cambia_el_codigo():
    plantilla = _u("f", "def f():\n    pass")   # stub de la plantilla
    alumno = _u("f", "def f():\n    return 42")  # implementado por el alumno
    assert firma_unidad(plantilla) != firma_unidad(alumno)


def test_java_soportado():
    assert ".java" in lenguajes_soportados()


def test_java_extrae_metodos_de_clase_grande(tmp_path):
    archivo = tmp_path / "Servicio.java"
    archivo.write_text(_CLASE_JAVA, encoding="utf-8")
    nombres = {u.nombre: u for u in extraer_unidades(archivo)}
    assert nombres["Servicio.sumarPositivos"].tipo == "metodo"
    assert nombres["Servicio.contiene"].num_ramas >= 1  # cuenta el for/if de Java
    # El Javadoc del método se extrae.
    assert nombres["Servicio.sumarPositivos"].docstring is not None
