"""T225: escribir_atomico reintenta os.replace ante PermissionError (WinError 5)."""

import os

import pytest

from nucleo import escritura


def _replace_que_falla(veces, error=PermissionError):
    real = os.replace
    llamadas = {"n": 0}

    def falso(a, b):
        llamadas["n"] += 1
        if llamadas["n"] <= veces:
            raise error(5, "Acceso denegado")
        return real(a, b)

    return falso, llamadas


def test_reintenta_y_escribe_si_el_bloqueo_es_pasajero(tmp_path, monkeypatch):
    destino = tmp_path / "tareas.json"
    destino.write_text("viejo", encoding="utf-8")
    falso, llamadas = _replace_que_falla(2)
    monkeypatch.setattr(escritura.os, "replace", falso)
    monkeypatch.setattr(escritura.time, "sleep", lambda s: None)

    escritura.escribir_atomico(destino, "nuevo")

    assert destino.read_text(encoding="utf-8") == "nuevo"
    assert llamadas["n"] == 3
    assert not list(tmp_path.glob(".*.tmp"))


def test_si_el_bloqueo_no_se_va_falla_y_no_deja_basura(tmp_path, monkeypatch):
    destino = tmp_path / "tareas.json"
    destino.write_text("viejo", encoding="utf-8")
    falso, llamadas = _replace_que_falla(99)
    monkeypatch.setattr(escritura.os, "replace", falso)
    monkeypatch.setattr(escritura.time, "sleep", lambda s: None)

    with pytest.raises(PermissionError):
        escritura.escribir_atomico(destino, "nuevo")

    assert destino.read_text(encoding="utf-8") == "viejo"
    assert llamadas["n"] == escritura.REINTENTOS_REPLACE
    assert not list(tmp_path.glob(".*.tmp"))


def test_otros_errores_no_se_reintentan(tmp_path, monkeypatch):
    destino = tmp_path / "tareas.json"
    falso, llamadas = _replace_que_falla(99, error=FileNotFoundError)
    monkeypatch.setattr(escritura.os, "replace", falso)
    monkeypatch.setattr(escritura.time, "sleep", lambda s: None)

    with pytest.raises(FileNotFoundError):
        escritura.escribir_atomico(destino, "nuevo")

    assert llamadas["n"] == 1


# T708: 23/09 un bloqueo de la guardia entro en bucle (mkstemp reintenta 10.000 veces ante
# PermissionError y algo de fuera lo repetia) y escribio un log de 280 GB.
def test_t708_crear_el_temporal_no_se_reintenta_ante_permiso_denegado(tmp_path, monkeypatch):
    real = os.open
    llamadas = {"n": 0}

    def falso(ruta, *a, **k):
        if str(ruta).endswith(".tmp"):
            llamadas["n"] += 1
            raise PermissionError(5, "Acceso denegado")
        return real(ruta, *a, **k)

    monkeypatch.setattr(escritura.os, "open", falso)
    with pytest.raises(PermissionError):
        escritura.escribir_atomico(tmp_path / "catalogo.md", "x")
    assert llamadas["n"] == 1
    assert not list(tmp_path.glob(".*.tmp"))


def test_t708_nombre_de_temporal_ocupado_se_reintenta_con_tope(tmp_path, monkeypatch):
    real = os.open
    llamadas = {"n": 0}

    def falso(ruta, *a, **k):
        if str(ruta).endswith(".tmp"):
            llamadas["n"] += 1
            raise FileExistsError(17, "existe")
        return real(ruta, *a, **k)

    monkeypatch.setattr(escritura.os, "open", falso)
    with pytest.raises(FileExistsError):
        escritura.escribir_atomico(tmp_path / "catalogo.md", "x")
    assert llamadas["n"] == escritura.INTENTOS_TEMPORAL


@pytest.mark.parametrize("base", [RuntimeError, PermissionError])
def test_t708_un_bloqueo_de_la_guardia_no_se_reintenta_nunca(tmp_path, monkeypatch, base):
    # Aunque la guardia heredase de PermissionError (como al principio), no cuenta como bloqueo pasajero.
    GuardiaBloqueo = type("GuardiaBloqueo", (base,), {})
    llamadas = {"n": 0}

    def falso(a, b):
        llamadas["n"] += 1
        raise GuardiaBloqueo("GUARDIA NEXO: bloqueado")

    monkeypatch.setattr(escritura.os, "replace", falso)
    monkeypatch.setattr(escritura.time, "sleep", lambda s: None)
    with pytest.raises(GuardiaBloqueo):
        escritura.escribir_atomico(tmp_path / "catalogo.md", "x")
    assert llamadas["n"] == 1
    assert not list(tmp_path.glob(".*.tmp"))
