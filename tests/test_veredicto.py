"""Tests de la deducción del veredicto a partir del texto del revisor."""

from generador import Veredicto
from generador.agentes import extraer_veredicto


def test_aprobada():
    texto = "VEREDICTO: APROBADA. La pregunta es clara y correcta."
    assert extraer_veredicto(texto) == Veredicto.APROBADA


def test_rechazada():
    texto = "VEREDICTO: RECHAZADA por contener un error técnico."
    assert extraer_veredicto(texto) == Veredicto.RECHAZADA


def test_aprobada_con_sugerencias():
    texto = "VEREDICTO: APROBADA CON SUGERENCIAS de redacción menores."
    assert extraer_veredicto(texto) == Veredicto.APROBADA_SUGERENCIAS


def test_rechazada_prevalece_sobre_aprobada():
    # El texto menciona 'aprobada' en una negación, pero el veredicto es de rechazo.
    texto = "La pregunta no puede ser aprobada.\nVEREDICTO: RECHAZADA."
    assert extraer_veredicto(texto) == Veredicto.RECHAZADA


def test_sin_marcador_recurre_al_texto_completo():
    texto = "En conjunto, la pregunta queda APROBADA."
    assert extraer_veredicto(texto) == Veredicto.APROBADA


def test_texto_no_concluyente():
    texto = "Comentario general sin una decisión explícita."
    assert extraer_veredicto(texto) == Veredicto.DESCONOCIDO
