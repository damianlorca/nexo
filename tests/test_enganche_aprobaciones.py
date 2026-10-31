# -*- coding: utf-8 -*-
"""Enganche de la cola de aprobaciones con manos/ (propuesta N04).

manos/servidor_mcp.py y nucleo/permisos.py son blindados: el enganche esta en
documentacion/propuestas/N04.patch, SIN aplicar. Por eso:
- los tests del enganche se SALTAN solos mientras el patch no este aplicado
  (incluido el del revisor de T154 F1, que el patch engancha en _puerta);
- el fallo que hay hoy (aprobado=True se salta tambien el rojo) va como xfail
  estricto: cuando alguien lo arregle, este test avisara para quitar la marca.

PowerShell no se ejecuta nunca: subprocess.run y shell.lanzar van con mocks.
"""
from __future__ import annotations

import subprocess

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="servidor_mcp necesita mcp<2 (FastMCP)")

from manos import servidor_mcp as srv, shell  # noqa: E402
from nucleo import aprobaciones as ap, permisos  # noqa: E402
from nucleo.config import RAIZ  # noqa: E402

PATCH_APLICADO = hasattr(srv, "_puerta")
con_patch = pytest.mark.skipif(not PATCH_APLICADO, reason="N04.patch no aplicado (blindados)")


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ALMACEN", tmp_path / "aprobaciones.json")
    monkeypatch.setattr(ap, "HISTORIAL", tmp_path / "aprobaciones_historial.jsonl")
    monkeypatch.setattr(ap, "CANDADO", tmp_path / ".candado.lock")
    # 27/09: sin esto, cada peticion ambar de estos tests pasaba por el revisor REAL y
    # contaba en memoria/revisor_estado.json: 5 en 10 min abrieron el disyuntor de verdad.
    from nucleo import revisor as rv
    monkeypatch.setattr(rv, "ESTADO", tmp_path / "revisor_estado.json")
    monkeypatch.setattr(rv, "CANDADO", tmp_path / ".candado_revisor.lock")
    monkeypatch.setattr(shell, "registrar_evidencia", lambda *a, **k: None)
    # config.toml trae la zona verde con rutas de Windows: en Linux la raiz quedaria fuera.
    monkeypatch.setattr(permisos, "zonas_verdes", lambda: [RAIZ])
    if hasattr(shell, "traza"):
        monkeypatch.setattr(shell, "traza", lambda *a, **k: None)


@pytest.fixture
def ejecutados(monkeypatch):
    """Lo que habria llegado a PowerShell."""
    lista = []

    def falso_run(args, **k):
        lista.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="hecho", stderr="")

    monkeypatch.setattr(shell.subprocess, "run", falso_run)
    return lista


# --------------------------------------------------------- fallo de hoy

@pytest.mark.xfail(
    not PATCH_APLICADO,
    strict=True,
    reason="BUG manos/shell.py:151 y :265: con aprobado=True no se llama a exigir() y el ROJO tambien pasa",
)
def test_aprobado_true_no_se_salta_el_rojo(ejecutados, monkeypatch):
    with pytest.raises(permisos.Bloqueado):
        shell.ejecutar("format C:", aprobado=True)

    monkeypatch.setattr(shell.subprocess, "Popen", lambda *a, **k: pytest.fail("se lanzo un rojo"))
    with pytest.raises(permisos.Bloqueado):
        shell.lanzar("format C:", aprobado=True)

    assert ejecutados == []


# ------------------------------------------------ con el patch aplicado

@con_patch
def test_ambar_sin_id_queda_en_cola_y_no_se_ejecuta(ejecutados):
    r = srv.comando("git push origin nube/N04")

    assert "SOLICITUD: A0001" in r
    assert ejecutados == []
    assert [s["detalle"] for s in ap.pendientes()] == ["git push origin nube/N04"]


@con_patch
def test_aprobado_true_ya_no_basta(ejecutados):
    r = srv.comando("git push origin nube/N04", aprobado=True)

    assert "ya no basta" in r
    assert ejecutados == []


@con_patch
def test_con_id_aprobado_se_ejecuta_una_sola_vez(ejecutados):
    srv.comando("git push origin nube/N04")
    ap.aprobar("A0001")

    assert "hecho" in srv.comando("git push origin nube/N04", aprobacion_id="A0001")
    assert len(ejecutados) == 1

    r = srv.comando("git push origin nube/N04", aprobacion_id="A0001")
    assert r.startswith("APROBACION NO VALIDA")
    assert len(ejecutados) == 1


@con_patch
def test_id_de_otra_accion_no_vale(ejecutados):
    srv.comando("git push origin nube/N04")
    ap.aprobar("A0001")

    r = srv.comando("git push --force origin principal", aprobacion_id="A0001")

    assert r.startswith("APROBACION NO VALIDA")
    assert ejecutados == []
    assert ap.ver("A0001")["estado"] == "aprobada"  # no se gasta en un intento malo


@con_patch
def test_id_sin_aprobar_no_vale(ejecutados):
    srv.comando("git push origin nube/N04")

    r = srv.comando("git push origin nube/N04", aprobacion_id="A0001")

    assert r.startswith("APROBACION NO VALIDA")
    assert ejecutados == []


@con_patch
def test_rojo_nunca_pasa(ejecutados):
    for kw in ({}, {"aprobado": True}, {"aprobacion_id": "A0001"}):
        r = srv.comando("format C:", **kw)
        assert r.startswith("BLOQUEADO"), kw

    assert ejecutados == []
    assert ap.pendientes() == []  # lo rojo ni se pregunta


@con_patch
def test_verde_va_directo(ejecutados):
    assert "hecho" in srv.comando("Get-Date")
    assert len(ejecutados) == 1
    assert ap.pendientes() == []


@con_patch
def test_lanzar_pasa_por_la_puerta(monkeypatch):
    lanzados = []
    monkeypatch.setattr(shell, "lanzar", lambda c, n, cwd, ok: lanzados.append((c, ok)) or {"pid": 1})

    assert "SOLICITUD" in srv.lanzar("winget install algo")
    ap.aprobar("A0001")
    srv.lanzar("winget install algo", aprobacion_id="A0001")

    assert lanzados == [("winget install algo", True)]


T861 = pytest.mark.skipif(
    "aprobacion_id" not in srv.escribir.__code__.co_varnames, reason="parche T861 no aplicado (blindados)"
)


@pytest.fixture
def ambar_en(tmp_path, monkeypatch):
    """Una ruta en tmp que manos ve como AMBAR (sin tocar nada real del proyecto)."""
    from manos import archivos

    destino = tmp_path / "blindado_falso.txt"

    def nivel(p, escritura=False):
        return permisos.Nivel.AMBAR if p == destino.resolve() else permisos.Nivel.VERDE

    monkeypatch.setattr(srv, "nivel_de_ruta", nivel)
    monkeypatch.setattr(archivos, "nivel_de_ruta", nivel)
    return destino


@T861
def test_escribir_ambar_sin_id_pide_aprobacion_y_no_escribe(ambar_en, monkeypatch):
    from nucleo import revisor as rv
    monkeypatch.setattr(rv, "procesar", lambda s: type("D", (), {"decision": "preguntar"})())

    r = srv.escribir(str(ambar_en), "hola")

    assert "SOLICITUD: A0001" in r
    assert not ambar_en.exists()
    assert ap.pendientes()[0]["detalle"].startswith(str(ambar_en.resolve()) + " sha256:")


@T861
def test_escribir_con_id_aprobado_escribe_ese_contenido_y_solo_una_vez(ambar_en, monkeypatch):
    from nucleo import revisor as rv
    monkeypatch.setattr(rv, "procesar", lambda s: type("D", (), {"decision": "preguntar"})())
    srv.escribir(str(ambar_en), "hola")
    ap.aprobar("A0001")

    # otro contenido con el mismo id: no vale y no gasta la aprobacion
    assert srv.escribir(str(ambar_en), "otra cosa", aprobacion_id="A0001").startswith("APROBACION NO VALIDA")
    assert not ambar_en.exists()

    srv.escribir(str(ambar_en), "hola", aprobacion_id="A0001")
    assert ambar_en.read_text(encoding="utf-8") == "hola"

    assert srv.escribir(str(ambar_en), "hola", aprobacion_id="A0001").startswith("APROBACION NO VALIDA")


@T861
def test_escribir_aprobado_nunca_salta_el_rojo(tmp_path, monkeypatch):
    from manos import archivos

    destino = tmp_path / "rojo.txt"
    monkeypatch.setattr(archivos, "nivel_de_ruta", lambda p, escritura=False: permisos.Nivel.ROJO)
    with pytest.raises(permisos.Bloqueado):
        archivos.escribir(destino, "x", aprobado=True)
    assert not destino.exists()


@con_patch
def test_la_cola_es_blindada():
    for rel in ("memoria/aprobaciones.json", "memoria/aprobaciones_historial.jsonl", "nucleo/aprobaciones.py"):
        assert permisos.nivel_de_ruta(RAIZ / rel, escritura=True) is permisos.Nivel.AMBAR, rel


@con_patch
def test_revisor_despacha_lo_de_la_lista_blanca(ejecutados, monkeypatch):
    from nucleo import revisor as rv
    monkeypatch.setattr(rv, "ESTADO", ap.ALMACEN.parent / "revisor_estado.json")
    monkeypatch.setattr(rv, "CANDADO", ap.ALMACEN.parent / ".candado_revisor.lock")

    assert "hecho" in srv.comando("pip install -r requisitos.txt")
    assert len(ejecutados) == 1

    s = ap.ver("A0001")
    assert s["estado"] == "usada"
    assert [e["quien"] for e in s["eventos"]] == ["mcp", "revisor:reglas", "sistema"]

    # lo que no esta en la lista blanca sigue esperando a Damian
    assert "SOLICITUD" in srv.comando("pip install requests")
    assert len(ejecutados) == 1


@con_patch
def test_lanzar_py_verde_no_pide_aprobacion_por_el_envoltorio_de_la_guardia(monkeypatch):
    """18/10 (A0071): un .py verde se lanza envuelto en la guardia sin crear solicitud ni quedarse en bucle."""
    lanzados = []
    monkeypatch.setattr(shell, "lanzar", lambda c, n, cwd, ok: lanzados.append((c, ok)) or {"pid": 1})

    r = srv.lanzar(r".venv\Scripts\python.exe herramientas_nube\estudio.py")

    assert "SOLICITUD" not in r
    assert ap.pendientes() == []
    assert len(lanzados) == 1
    comando, ok = lanzados[0]
    assert "guardia_python.py" in comando and comando.endswith(r"herramientas_nube\estudio.py") and ok is True


@con_patch
def test_lanzar_ambar_aprobado_se_lanza_sin_envoltorio(monkeypatch):
    lanzados = []
    monkeypatch.setattr(shell, "lanzar", lambda c, n, cwd, ok: lanzados.append((c, ok)) or {"pid": 1})

    assert "SOLICITUD" in srv.lanzar("winget install algo")
    ap.aprobar("A0001")
    srv.lanzar("winget install algo", aprobacion_id="A0001")

    assert lanzados == [("winget install algo", True)]


# ------------------------------------------------ T1020: motivo y guardian (pieza 4, blindado)

@con_patch
def test_t1020_el_motivo_queda_en_la_solicitud_y_no_en_la_huella(ejecutados):
    r = srv.comando("winget install algo", motivo="  para   probar el guardian ")
    s = ap.cargar()["solicitudes"][-1]
    assert "NECESITA APROBACION" in r and ejecutados == []
    assert s["extra"]["motivo"] == "para probar el guardian"
    assert s["huella"] == ap.huella("ejecutar comando", "winget install algo")


@con_patch
def test_t1020_lo_que_el_guardian_aprueba_se_ejecuta_sin_esperar(ejecutados, monkeypatch):
    from nucleo import guardian
    monkeypatch.setattr(guardian, "GANCHO", True)
    monkeypatch.setattr(guardian, "ESTADO", ap.ALMACEN.with_name("guardian.json"))
    cmd = "Select-String -Path memoria\\aprobaciones.json -Pattern 'MiroFish' | Select-Object -First 3"
    assert permisos.nivel_de_comando(cmd) is permisos.Nivel.AMBAR      # nombra un blindado: llega a la cola
    r = srv.comando(cmd, motivo="ver que pidio MiroFish")
    s = ap.cargar()["solicitudes"][-1]
    assert "NECESITA" not in r and len(ejecutados) == 1
    assert s["estado"] == "usada" and s["decidida_por"] == "guardian"
    assert s["extra"]["motivo"] == "ver que pidio MiroFish"


@con_patch
def test_t1020_leer_fuera_de_la_zona_guarda_el_motivo(monkeypatch):
    fuera = RAIZ.parent / "herramientas_externas" / "x" / ".env.example"
    r = srv.leer(str(fuera), motivo="ver la plantilla")
    s = ap.cargar()["solicitudes"][-1]
    assert "NECESITA APROBACION" in r and s["accion"] == "leer" and s["extra"]["motivo"] == "ver la plantilla"


# ------------------------------------------------ T1025: leer con aprobacion (manos blindadas: parche aparte)

T1025 = pytest.mark.skipif(
    "aprobacion_id" not in srv.leer.__code__.co_varnames,
    reason="parche documentacion/diffs/T1025_leer_aprobado.patch no aplicado (blindados)",
)


@T1025
def test_t1025_leer_ambar_sin_id_pide_aprobacion_y_no_lee(ambar_en, monkeypatch):
    from nucleo import revisor as rv
    monkeypatch.setattr(rv, "procesar", lambda s: type("D", (), {"decision": "preguntar"})())
    ambar_en.write_text("contenido de fuera", encoding="utf-8")

    r = srv.leer(str(ambar_en), motivo="ver la plantilla")

    assert "SOLICITUD: A0001" in r and "contenido de fuera" not in r
    s = ap.pendientes()[0]
    assert (s["accion"], s["detalle"], s["extra"]["motivo"]) == ("leer", str(ambar_en.resolve()), "ver la plantilla")


@T1025
def test_t1025_leer_con_id_aprobado_lee_esa_ruta_y_solo_una_vez(ambar_en, monkeypatch, tmp_path):
    from manos import archivos
    from nucleo import revisor as rv
    monkeypatch.setattr(rv, "procesar", lambda s: type("D", (), {"decision": "preguntar"})())

    def nivel(p, escritura=False):          # las dos rutas de este test, fuera de las carpetas de NEXO
        return permisos.Nivel.AMBAR if tmp_path in p.parents else permisos.Nivel.VERDE
    monkeypatch.setattr(srv, "nivel_de_ruta", nivel)
    monkeypatch.setattr(archivos, "nivel_de_ruta", nivel)
    ambar_en.write_text("contenido de fuera", encoding="utf-8")
    srv.leer(str(ambar_en))
    ap.aprobar("A0001")

    otra = tmp_path / "otra.txt"            # la aprobacion va atada a la ruta: otra no vale y no la gasta
    otra.write_text("otra", encoding="utf-8")
    assert srv.leer(str(otra), aprobacion_id="A0001").startswith("APROBACION NO VALIDA")

    assert srv.leer(str(ambar_en), aprobacion_id="A0001") == "contenido de fuera"
    assert srv.leer(str(ambar_en), aprobacion_id="A0001").startswith("APROBACION NO VALIDA")


@T1025
def test_t1025_lo_que_el_guardian_aprueba_se_lee_a_la_primera(monkeypatch, tmp_path):
    """El caso de A0066: lectura en herramientas_externas, el guardian la aprueba al entrar y se lee sin esperar."""
    from nucleo import guardian
    externas = tmp_path / "herramientas_externas"
    archivo = externas / "MiroFish" / ".env.example"
    archivo.parent.mkdir(parents=True)
    archivo.write_text("CLAVE=pon_aqui_la_tuya", encoding="utf-8")
    monkeypatch.setattr(guardian, "EXTERNAS", externas)
    monkeypatch.setattr(guardian, "GANCHO", True)
    monkeypatch.setattr(guardian, "ESTADO", ap.ALMACEN.with_name("guardian.json"))
    assert permisos.nivel_de_ruta(archivo, escritura=False) is permisos.Nivel.AMBAR   # fuera de las carpetas de NEXO

    r = srv.leer(str(archivo), motivo="ver que variables pide MiroFish")

    s = ap.cargar()["solicitudes"][-1]
    assert r == "CLAVE=pon_aqui_la_tuya"
    assert s["estado"] == "usada" and s["decidida_por"] == "guardian"


@T1025
def test_t1025_leer_aprobado_nunca_salta_el_rojo(tmp_path, monkeypatch):
    from manos import archivos
    secreto = tmp_path / "secretos.toml"
    secreto.write_text("x = 'falso'", encoding="utf-8")
    monkeypatch.setattr(archivos, "_resolver", lambda r: secreto)

    r = srv.leer(str(secreto), aprobacion_id="A0001")      # ni con un id: el rojo no llega a la puerta

    assert r.startswith("BLOQUEADO (rojo)") and "falso" not in r
    assert ap.cargar()["solicitudes"] == []


# ------------------------------------------------ T1025 (2): listar con aprobacion, como leer

T1025_LISTAR = pytest.mark.skipif(
    "aprobacion_id" not in srv.listar.__code__.co_varnames,
    reason="parche documentacion/diffs/T1025_listar_aprobado.patch no aplicado (blindados)",
)


@T1025_LISTAR
def test_t1025_listar_fuera_sin_id_pide_aprobacion_y_con_id_lista_una_vez(monkeypatch, tmp_path):
    from manos import archivos
    from nucleo import revisor as rv
    monkeypatch.setattr(rv, "procesar", lambda s: type("D", (), {"decision": "preguntar"})())
    fuera = tmp_path / "fuera"
    (fuera / "sub").mkdir(parents=True)
    (fuera / "sub" / "a.py").write_text("x = 1\n", encoding="utf-8")

    def nivel(p, escritura=False):
        return permisos.Nivel.AMBAR if tmp_path in p.parents or p == tmp_path else permisos.Nivel.VERDE
    monkeypatch.setattr(srv, "nivel_de_ruta", nivel)
    monkeypatch.setattr(archivos, "nivel_de_ruta", nivel)

    r = srv.listar(str(fuera), "*.py", motivo="ver que trae")
    assert "SOLICITUD: A0001" in r and "a.py" not in r
    s = ap.pendientes()[0]
    assert (s["accion"], s["detalle"], s["extra"]["motivo"]) == ("listar", str(fuera.resolve()), "ver que trae")
    ap.aprobar("A0001")
    assert srv.listar(str(tmp_path), "*.py", aprobacion_id="A0001").startswith("APROBACION NO VALIDA")  # otra carpeta
    assert srv.listar(str(fuera), "*.py", aprobacion_id="A0001").replace("\\", "/") == "sub/a.py"
    assert srv.listar(str(fuera), "*.py", aprobacion_id="A0001").startswith("APROBACION NO VALIDA")     # gastada


@T1025_LISTAR
def test_t1025_listar_lo_que_el_guardian_aprueba_se_lista_a_la_primera(monkeypatch, tmp_path):
    from nucleo import guardian
    externas = tmp_path / "herramientas_externas"
    (externas / "MiroFish").mkdir(parents=True)
    (externas / "MiroFish" / "leeme.md").write_text("hola", encoding="utf-8")
    monkeypatch.setattr(guardian, "EXTERNAS", externas)
    monkeypatch.setattr(guardian, "GANCHO", True)
    monkeypatch.setattr(guardian, "ESTADO", ap.ALMACEN.with_name("guardian.json"))

    r = srv.listar(str(externas / "MiroFish"), motivo="ver que trae MiroFish")

    s = ap.cargar()["solicitudes"][-1]
    assert r == "leeme.md" and s["estado"] == "usada" and s["decidida_por"] == "guardian"
