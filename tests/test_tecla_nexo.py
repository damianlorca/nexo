"""24/10: la tecla Copilot es un interruptor de la ventana de NEXO (interfaz/tecla.py)."""
from interfaz import tecla


def test_decidir_abre_trae_o_minimiza():
    assert tecla.decidir(existe=False, minimizada=False, delante=False) == "abrir"
    assert tecla.decidir(existe=True, minimizada=True, delante=False) == "traer"
    assert tecla.decidir(existe=True, minimizada=False, delante=False) == "traer"
    assert tecla.decidir(existe=True, minimizada=False, delante=True) == "minimizar"


def test_solo_reconoce_la_ventana_de_aplicacion_de_edge():
    assert tecla.es_ventana_nexo("Centro · NEXO", "msedge.exe")
    assert tecla.es_ventana_nexo("Tareas · NEXO", "MSEDGE.EXE")
    assert not tecla.es_ventana_nexo("Centro · NEXO - Personal: Microsoft Edge", "msedge.exe")   # pestana normal
    assert not tecla.es_ventana_nexo("Centro · NEXO", "chrome.exe")
    assert not tecla.es_ventana_nexo("Mi documento", "msedge.exe")
