# -*- coding: utf-8 -*-
"""T1069 (Bloque 20, 25/10): los turnos de noche se reparten el tiempo y el reparto de reels no ensucia principal.

La noche del 25/10 el lote de reels encadeno lotes de 02:00 a pasadas las 10:00 y el implementador y el tribunal
esperaron en cola casi toda la noche (1 fusion); ademas nucleo/reels_destino.py dejaba el catalogo y las guias sin
commit y el implementador se paraba con "principal tiene cambios sin commit". Todo con dobles: reloj y cola falsos,
sin procesos, sin red y con un repo git de juguete (nunca el real).

Contrato pieza 1:
- planificador.ceder(turno, fin): si en la cola espera algo que saldria antes (manual o menor prioridad) y nada lo
  retiene (PARADA, interruptor, freno F0 en las generadoras, `no_antes`), vuelve a encolar el turno con `fin` (su
  ventana; nunca se alarga) y devuelve a quien cede. Lo lanzado a mano no cede. Con menos de MIN_RESTO minutos de
  ventana no vuelve a la cola (la entrada caduca). Una hora programada nueva sustituye al resto de una ventana cedida.
- reels.turno(ceder=...): el lote va por tramos que acaban a la hora en punto (--hasta) y solo tras un tramo que acabo
  por la hora pregunta si cede. Sin `ceder`, un solo tramo hasta el tope (como antes).
- Una noche simulada con reels, implementador y tribunal cada hora: los tres corren en cada hora de reloj.
Contrato pieza 2:
- reels_destino.guardar_en_git: commit propio SOLO del catalogo y documentacion/guias/*.md que cambiaron; nunca
  memoria/ ni otros archivos (aunque esten sucios o en el indice). Revision de privacidad de las lineas nuevas (codigo
  de reel, @cuenta, URL de red, perfil_privado): si encuentra algo, sin commit y aviso en el Centro (sin el dato).
- puerta.arbol_limpio: el catalogo y las guias sucias no bloquean SOLO mientras hay un reparto en marcha.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from extremidades import reels
from nucleo import planificador as P
from nucleo import reels_destino as D
from nucleo import turnos
from tests.test_bloque18_reels import _e, _ficha, _guardar_ficha, _pedir_por_ficha

NOCHE = datetime(2026, 10, 25, 23, 0)


def _turno(plantilla, horas, max_minutos, nombre=None):
    return turnos.guardar_turno({"nombre": nombre or plantilla, "plantilla": plantilla, "dias": list(turnos.DIAS),
                                 "horas": horas, "max_minutos": max_minutos})


def _entrada(turno_id, cuando, **extra):
    return {"turno": turno_id, "manual": False, "pedido": cuando.isoformat(timespec="seconds"), **extra}


def _poner_cola(*entradas):
    est = P.estado()
    est["cola"] = list(entradas)
    P._escribir(P.ESTADO, est)


# ------------------------------------------------------------------ pieza 1: ceder
def test_cede_solo_si_espera_alguien_que_va_antes_y_vuelve_detras_con_su_ventana():
    rl = _turno("reels", ["23:30"], 180)
    otro_rl = _turno("reels", ["10:31"], 30, "Reels de dia")
    impl = _turno("implementador", ["03:00"], 25)
    ahora, fin = NOCHE + timedelta(hours=1), NOCHE + timedelta(hours=3, minutes=30)
    assert P.ceder(rl["id"], fin, ahora=ahora) == []                           # cola vacia: sigue
    _poner_cola(_entrada(otro_rl["id"], ahora - timedelta(minutes=30)))
    assert P.ceder(rl["id"], fin, ahora=ahora) == []                           # otro lote de reels: no va antes
    _poner_cola(_entrada(otro_rl["id"], ahora - timedelta(minutes=30)), _entrada(impl["id"], ahora))
    assert P.ceder(rl["id"], fin, ahora=ahora) == [impl["id"]]
    vuelta = [x for x in P.cola() if x["turno"] == rl["id"]]
    assert vuelta == [{"turno": rl["id"], "manual": False, "pedido": ahora.isoformat(timespec="seconds"),
                       "cedido": True, "fin": fin.isoformat(timespec="seconds")}]
    assert P.estado()["cedidos"][-1]["a"] == [impl["id"]]
    cfg = turnos.cargar()                                                     # sale detras del implementador
    assert sorted(P.cola(), key=lambda x: P._orden_cola(x, cfg))[0]["turno"] == impl["id"]


def test_no_cede_lo_manual_ni_con_parada_ni_por_una_generadora_frenada(monkeypatch):
    from nucleo import freno, parada
    rl = _turno("reels", ["23:30"], 180)
    rev = _turno("revisar_codigo", ["05:45"], 45)
    impl = _turno("implementador", ["03:00"], 25)
    ahora, fin = NOCHE, NOCHE + timedelta(hours=2)
    _poner_cola(_entrada(impl["id"], ahora))
    assert P.ceder(rl["id"], fin, manual=True, ahora=ahora) == []             # "Lanzar ya" de Damian: no cede
    monkeypatch.setattr(parada, "activa", lambda: "me voy")
    assert P.ceder(rl["id"], fin, ahora=ahora) == []                          # con PARADA nadie saldria
    monkeypatch.setattr(parada, "activa", lambda: None)
    _poner_cola(_entrada(impl["id"], ahora, no_antes=(ahora + timedelta(hours=1)).isoformat()))
    assert P.ceder(rl["id"], fin, ahora=ahora) == []                          # pospuesto: aun no esta listo
    monkeypatch.setattr(P, "PRIORIDAD", dict(P.PRIORIDAD, revisar_codigo=3))  # por delante de reels (4)...
    monkeypatch.setattr(freno, "puede_generar", lambda pl: (False, "freno F0"))
    _poner_cola(_entrada(rev["id"], ahora))
    assert P.ceder(rl["id"], fin, ahora=ahora) == []                          # ...pero el freno no la dejaria salir
    _poner_cola(_entrada(rev["id"], ahora, manual=True))
    assert P.ceder(rl["id"], fin, ahora=ahora) == [rev["id"]]                 # lo manual si (salta el freno)
    turnos.desactivar("de viaje")
    _poner_cola(_entrada(impl["id"], ahora))
    assert P.ceder(rl["id"], fin, ahora=ahora) == []                          # interruptor apagado: no saldria


def test_vuelve_con_lo_que_le_quedaba_y_caduca_sin_ventana(monkeypatch):
    rl = _turno("reels", ["23:30"], 180)
    ahora, fin = NOCHE, NOCHE + timedelta(minutes=50)
    _poner_cola(_entrada(rl["id"], ahora, cedido=True, fin=fin.isoformat(timespec="seconds")))
    lanzados = []
    hecho = P.tick(ahora, lanzar=lambda e: lanzados.append(e) or 99999999)
    assert hecho["lanzado"] == rl["id"] and lanzados[0]["fin"] == fin.isoformat(timespec="seconds")
    assert json.loads(P.EN_MARCHA.read_text(encoding="utf-8"))["max_minutos"] == 50   # no 180
    P.terminar()
    _poner_cola(_entrada(rl["id"], ahora, cedido=True, fin=(ahora + timedelta(minutes=9)).isoformat()))
    assert P.tick(ahora + timedelta(seconds=20), lanzar=lanzados.append)["lanzado"] is None and P.cola() == []
    assert P.minutos_hasta(None, 30) == 30 and P.minutos_hasta(fin.isoformat(), 30, ahora) == 30
    # el planificador se lo pasa a turno_nexo, que recorta su tope
    llamadas = []
    monkeypatch.setattr(P, "_popen", lambda args, **k: llamadas.append(args) or SimpleNamespace(pid=1))
    P.lanzar_proceso({"turno": rl["id"], "fin": fin.isoformat()})
    assert f"--fin={fin.isoformat()}" in llamadas[0]


def test_una_hora_programada_nueva_sustituye_al_resto_cedido(monkeypatch):
    import time
    rl = _turno("reels", ["02:30"], 180)
    P.tick(datetime(2026, 10, 26, 2, 29), lanzar=lambda e: 99999999)            # primer tick (sin cola)
    _poner_cola(_entrada(rl["id"], datetime(2026, 10, 26, 2, 0), cedido=True, fin="2026-10-26T02:45:00"))
    P._escribir(P.EN_MARCHA, {"turno": "otro", "lanzado": time.time(), "pid": 1, "max_minutos": 30})
    monkeypatch.setattr(P, "_vivo", lambda pid: True)                         # hay otro en marcha
    P.tick(datetime(2026, 10, 26, 2, 30, 10), lanzar=lambda e: pytest.fail("hay uno en marcha"))
    assert [(x["turno"], x.get("cedido")) for x in P.cola()] == [(rl["id"], None)]


# ------------------------------------------------------------------ pieza 1: el lote por tramos
class Reloj:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def lote_falso(monkeypatch, tmp_path):
    """reels.turno con la cola de reels, propuestas y huecos de mentira (nada real)."""
    from nucleo import reels_huecos, reels_tareas
    monkeypatch.setattr(reels, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(reels, "LOTE", tmp_path / "lote.json")
    monkeypatch.setattr(reels, "cola_lote", lambda *a, **k: ["R1"])
    # Bloque 21: sin esto leia la coleccion privada real (no existe en los worktrees: linea base en rojo)
    monkeypatch.setattr(reels, "cola_rehacer", lambda *a, **k: [])
    monkeypatch.setattr(reels_tareas, "cargar_fichas", lambda c: [{"codigo": x, "elementos": []} for x in c])
    monkeypatch.setattr(reels_tareas, "plan", lambda f: {"tareas": []})
    monkeypatch.setattr(reels_tareas, "crear", lambda p: {"creadas": []})
    monkeypatch.setattr(reels_huecos, "registrar", lambda f: {"tarjeta": {}})


def test_proxima_hora_en_punto():
    assert reels.proxima_hora(datetime(2026, 10, 26, 2, 30)) == datetime(2026, 10, 26, 3, 0)
    assert reels.proxima_hora(datetime(2026, 10, 26, 2, 57)) == datetime(2026, 10, 26, 4, 0)
    assert reels.proxima_hora(datetime(2026, 10, 26, 23, 40)) == datetime(2026, 10, 27, 0, 0)


def test_el_lote_va_por_tramos_a_la_hora_en_punto_y_cede_entre_tramos(lote_falso):
    reloj = Reloj(datetime(2026, 10, 25, 23, 30))
    ordenes, preguntas = [], []

    def correr(args, **k):
        ordenes.append(args)
        reloj.t = reels.leer_hasta(args[args.index("--hasta") + 1], reloj.t)   # el tramo corre hasta su hora
        n = len(ordenes)
        return SimpleNamespace(stdout=json.dumps({"hechos": [f"R{n}"], "fallos": [], "motivo_fin": "hora limite"}),
                               returncode=0, stderr="")

    def ceder():
        preguntas.append(reloj.t)
        return ["implpil2"] if len(preguntas) == 2 else []
    r = reels.turno(correr=correr, minutos=180, ceder=ceder, ahora=reloj, repartir=lambda c: {"recuento": {}})
    assert [o[o.index("--hasta") + 1] for o in ordenes] == ["00:00", "01:00"]
    assert [o[o.index("--max") + 1] for o in ordenes] == ["60", "59"]            # el tope se reparte entre tramos
    assert preguntas == [datetime(2026, 10, 26, 0, 0), datetime(2026, 10, 26, 1, 0)]
    assert r["cedido"] == ["implpil2"] and r["noche"]["hechos"] == ["R1", "R2"] and r["noche"]["tramos"] == 2
    assert r["noche"]["motivo_fin"] == "cede el turno a implpil2"


def test_el_ultimo_tramo_acaba_en_el_tope_y_sin_ceder_es_un_solo_lote(lote_falso):
    reloj = Reloj(datetime(2026, 10, 26, 2, 10))
    ordenes = []

    def correr(args, **k):
        ordenes.append(args)
        reloj.t = reels.leer_hasta(args[args.index("--hasta") + 1], reloj.t)
        return SimpleNamespace(stdout=json.dumps({"hechos": [], "fallos": [], "motivo_fin": "hora limite"}),
                               returncode=0, stderr="")
    reels.turno(correr=correr, minutos=20, ceder=lambda: pytest.fail("sin ventana no se pregunta"), ahora=reloj)
    assert [o[o.index("--hasta") + 1] for o in ordenes] == ["02:24"]
    ordenes.clear()
    reloj.t = datetime(2026, 10, 25, 23, 30)
    reels.turno(correr=correr, minutos=180, ahora=reloj)                        # sin ceder: como antes
    assert [o[o.index("--hasta") + 1] for o in ordenes] == ["02:24"]


def test_no_pregunta_si_el_tramo_acabo_por_otra_cosa(lote_falso):
    reloj = Reloj(datetime(2026, 10, 25, 23, 30))

    def correr(args, **k):
        return SimpleNamespace(stdout=json.dumps({"hechos": ["R1"], "fallos": [], "motivo_fin": "cola vacia"}),
                               returncode=0, stderr="")
    r = reels.turno(correr=correr, minutos=180, ceder=lambda: pytest.fail("no toca"), ahora=reloj,
                    repartir=lambda c: {"recuento": {}})
    assert r["noche"]["motivo_fin"] == "cola vacia" and "cedido" not in r


def test_rehacer_tambien_va_por_tramos(monkeypatch, tmp_path):
    monkeypatch.setattr(reels, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(reels, "REHACER", tmp_path / "rehacer.json")
    monkeypatch.setattr(reels, "cola_lote", lambda *a, **k: [])
    monkeypatch.setattr(reels, "cola_rehacer", lambda *a, **k: ["V1", "V2"])
    reloj = Reloj(datetime(2026, 10, 26, 3, 40))
    ordenes = []

    def correr(args, **k):
        ordenes.append(args)
        reloj.t += timedelta(minutes=int(args[args.index("--minutos") + 1]))
        return SimpleNamespace(stdout=json.dumps({"hechos": ["V1"], "fallos": [], "motivo_fin": "hora limite",
                                                  "quedan": 1}), returncode=0, stderr="")
    r = reels.turno(correr=correr, minutos=60, ceder=lambda: ["u1ecd7c"], ahora=reloj)
    assert [o[o.index("--minutos") + 1] for o in ordenes] == ["20"] and r["cedido"] == ["u1ecd7c"]


# ------------------------------------------------------------------ pieza 1: una noche simulada
def test_noche_simulada_reels_implementador_y_tribunal_corren_cada_hora(monkeypatch, lote_falso):
    """Reels con tres ventanas de 180 min (23:30, 02:30, 05:30), implementador a las y 05 y tribunal a las y 35, todas
    las horas. Antes de T1069 el lote ocupaba cada ventana entera; ahora cada uno corre en cada hora de reloj."""
    from nucleo import cierre_auto, enrutado, espejo, guardian, responsables, vigia_disco
    for mod, fn in ((responsables, "repaso_si_toca"), (cierre_auto, "repaso_si_toca"), (espejo, "repaso_si_toca"),
                    (guardian, "barrido_si_toca"), (enrutado, "avisar_sin_turno"), (vigia_disco, "revisar")):
        monkeypatch.setattr(mod, fn, lambda *a, **k: None)
    for fn in ("_cerrar_por_tope", "_forzar_si_toca", "_vigilar_latido", "_vigilar_progreso"):
        monkeypatch.setattr(P, fn, lambda *a, **k: None)
    vivos: set = set()
    monkeypatch.setattr(P, "_vivo", lambda pid: pid in vivos)
    rl = _turno("reels", ["23:30", "02:30", "05:30"], 180)
    impl = _turno("implementador", [f"{h:02d}:05" for h in range(24)], 25)
    trib = _turno("tribunal", [f"{h:02d}:35" for h in range(24)], 20)
    dura = {impl["id"]: 5, trib["id"]: 10}
    reloj = Reloj(NOCHE)
    lanzados, limites = [], []

    def lanzar(entrada):
        assert not vivos, "dos turnos a la vez"
        lanzados.append((entrada["turno"], reloj.t, dict(entrada)))
        vivos.add(4242)
        return 4242

    def avanzar(hasta):
        while reloj.t < hasta:
            reloj.t += timedelta(minutes=1)
            P.tick(reloj.t, lanzar=lanzar)

    def correr(args, **k):           # el lote "trabaja" hasta su --hasta mientras el planificador sigue encolando
        avanzar(reels.leer_hasta(args[args.index("--hasta") + 1], reloj.t))
        return SimpleNamespace(stdout=json.dumps({"hechos": ["R"], "fallos": [], "motivo_fin": "hora limite"}),
                               returncode=0, stderr="")
    P.tick(reloj.t - timedelta(minutes=1), lanzar=lanzar)
    fin_noche = datetime(2026, 10, 26, 7, 0)
    while reloj.t < fin_noche:
        if P.tick(reloj.t, lanzar=lanzar)["lanzado"]:
            tid, t0, entrada = lanzados[-1]
            if tid == rl["id"]:          # lo que hace turno_nexo con el turno de reels
                minutos = P.minutos_hasta(entrada.get("fin"), 180, t0)
                limite = t0 + timedelta(minutes=minutos)
                limites.append((t0, limite))
                reels.turno(correr=correr, minutos=minutos, ahora=reloj, repartir=lambda c: {"recuento": {}},
                            ceder=lambda: P.ceder(rl["id"], limite, ahora=reloj.t))
            else:
                avanzar(t0 + timedelta(minutes=dura[tid]))
            vivos.clear()
            P.terminar()
        else:
            reloj.t += timedelta(minutes=1)      # con nada en marcha, el tick de arriba es el que lanza
    for h in range(7):               # 00:00 .. 06:59
        ini = datetime(2026, 10, 26, h, 0)
        en_la_hora = {tid for tid, t0, _ in lanzados if ini <= t0 < ini + timedelta(hours=1)}
        assert {rl["id"], impl["id"], trib["id"]} <= en_la_hora, f"{ini:%H:%M}: {en_la_hora}"
    # la ventana de reels nunca se alarga: cada vuelta acaba dentro de la ventana de 180 min de su hora programada
    ventanas = [datetime(2026, 10, 25, 23, 30), datetime(2026, 10, 26, 2, 30), datetime(2026, 10, 26, 5, 30)]
    assert len(limites) > 3
    for t0, limite in limites:
        assert limite <= max(v for v in ventanas if v <= t0) + timedelta(minutes=180)


# ------------------------------------------------------------------ pieza 2: commit propio del reparto
def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          encoding="utf-8").stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Repo de juguete con la forma de NEXO: catalogo y guias en git, memoria/ privada, y el almacen de destinos."""
    r = tmp_path / "agente"
    archivos = {"documentacion/CATALOGO_HERRAMIENTAS.md": "# Catálogo\n\n## 1. Para hacer X, usa Y\n\n| Graft | x |\n",
                "documentacion/guias/prompts.md": "# Prompts\n",
                "nucleo/cola.py": "x = 1\n", "memoria/tareas.json": "{}\n"}
    for ruta, texto in archivos.items():
        (r / ruta).parent.mkdir(parents=True, exist_ok=True)
        (r / ruta).write_text(texto, encoding="utf-8")
    _git(r, "init", "-q", "-b", "principal")
    _git(r, "add", "-A")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    carpeta = r / "memoria" / "perfil_privado" / "reels"
    carpeta.mkdir(parents=True)
    monkeypatch.setattr(D, "REPO", r)
    monkeypatch.setattr(D, "CARPETA", carpeta)
    monkeypatch.setattr(D, "ALMACEN", carpeta / "destinos.json")
    monkeypatch.setattr(D, "CATALOGO_MD", r / "documentacion" / "CATALOGO_HERRAMIENTAS.md")
    monkeypatch.setattr(D, "GUIAS", r / "documentacion" / "guias")
    monkeypatch.setattr(D, "CHINA_MD", r / "memoria" / "perfil_privado" / "viajes" / "china.md")
    monkeypatch.setattr(D, "MONETIZACION_MD", r / "memoria" / "perfil_privado" / "monetizacion" / "m.md")
    (carpeta / "reels_coleccion.json").write_text(json.dumps({"reels": [{"codigo": "CodAI0001"},
                                                                        {"codigo": "CodCH0002"}]}), encoding="utf-8")
    return r


def _repartir():
    return D.repartir(pedir=_pedir_por_ficha([]), catalogo_items=[], tareas=[], reg=[], crear=False,
                      parada=lambda: False)


def test_tras_un_lote_principal_queda_limpio_y_el_commit_es_solo_del_reparto(repo):
    from nucleo import puerta
    (repo / "memoria" / "tareas.json").write_text('{"sucio": 1}\n', encoding="utf-8")   # NEXO escribe memoria/
    (repo / "nucleo" / "cola.py").write_text("x = 2\n", encoding="utf-8")               # otro, en el indice
    _git(repo, "add", "nucleo/cola.py")
    _guardar_ficha(D.CARPETA, _ficha("CodAI0001"))
    _guardar_ficha(D.CARPETA, _ficha("CodCH0002", ["China comunista"], [_e("dato", "Metro de Shanghái")],
                                     tema="Moverse por China"))
    r = _repartir()
    assert r["hechos"] == 2 and r["git"]["estado"] == "commit"
    hecho = _git(repo, "show", "--name-only", "--format=%an", "HEAD").split()
    assert hecho[0] == "NEXO" and sorted(hecho[4:]) == ["documentacion/CATALOGO_HERRAMIENTAS.md",
                                                        "documentacion/guias/prompts.md"]
    estado = dict((l[3:], l[:2]) for l in _git(repo, "status", "--porcelain", "--untracked-files=no").splitlines())
    assert estado == {"memoria/tareas.json": " M", "nucleo/cola.py": "M "}   # lo ajeno, intacto (y en el indice)
    _git(repo, "reset", "-q", "nucleo/cola.py")
    _git(repo, "checkout", "-q", "--", "nucleo/cola.py")
    assert puerta.arbol_limpio(repo)                       # para el implementador, principal queda limpio
    assert _repartir()["git"] == {"estado": "sin_cambios"}  # otra tanda sin nada nuevo: ni commit vacio


def test_guia_nueva_sin_seguimiento_tambien_entra(repo):
    _git(repo, "rm", "-q", "documentacion/guias/prompts.md")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "sin guia")
    _guardar_ficha(D.CARPETA, _ficha("CodAI0001"))
    assert _repartir()["git"]["estado"] == "commit"
    assert "documentacion/guias/prompts.md" in _git(repo, "show", "--name-only", "--format=", "HEAD")
    assert _git(repo, "status", "--porcelain", "--", "documentacion") == ""


@pytest.mark.parametrize("malo, tipo", [("prueba CodAI0001", "codigo de reel"), ("de @creador_ia", "@cuenta"),
                                        ("ver https://www.instagram.com/p/x", "URL de red social"),
                                        ("sale de memoria/perfil_privado/reels", "perfil_privado")])
def test_la_revision_de_privacidad_para_el_commit_y_avisa_sin_el_dato(repo, tmp_path, malo, tipo):
    from nucleo import avisos
    guia = repo / "documentacion" / "guias" / "prompts.md"
    guia.write_text(guia.read_text(encoding="utf-8") + f"- {malo}\n", encoding="utf-8")
    antes = _git(repo, "rev-parse", "HEAD")
    r = D.guardar_en_git([str(guia)])
    assert r["estado"] == "privacidad" and r["problemas"] == [f"documentacion/guias/prompts.md:2: {tipo}"]
    assert _git(repo, "rev-parse", "HEAD") == antes and "prompts.md" in _git(repo, "status", "--porcelain")
    texto = " ".join(p.read_text(encoding="utf-8") for p in avisos.CARPETA.rglob("*.json"))
    assert "no se ha guardado en git" in texto and "CodAI0001" not in texto and "@creador_ia" not in texto


def test_lo_que_ya_estaba_en_git_no_cuenta_y_el_arroba_de_un_paquete_no_es_una_cuenta(repo):
    cat = repo / "documentacion" / "CATALOGO_HERRAMIENTAS.md"
    cat.write_text(cat.read_text(encoding="utf-8") + "- `npx skills add owner/repo@skill`\n", encoding="utf-8")
    assert D.guardar_en_git([str(cat)])["estado"] == "commit"


def test_nunca_mete_rutas_que_no_son_suyas(repo):
    otro = repo / "nucleo" / "cola.py"
    otro.write_text("x = 3\n", encoding="utf-8")
    privado = repo / "memoria" / "tareas.json"
    privado.write_text('{"x": 2}\n', encoding="utf-8")
    assert D.guardar_en_git([str(otro), str(privado), str(repo.parent / "fuera.md")]) == {"estado": "nada"}
    assert D.es_generado("documentacion/guias/prompts.md") and not D.es_generado("documentacion/guias/a/b.md")
    assert not D.es_generado("documentacion/OTRO.md") and not D.es_generado("memoria/perfil_privado/viajes/china.md")


def test_un_fallo_de_git_no_rompe_la_tanda(repo, monkeypatch):
    cat = repo / "documentacion" / "CATALOGO_HERRAMIENTAS.md"
    cat.write_text(cat.read_text(encoding="utf-8") + "- algo\n", encoding="utf-8")
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")            # otro git a medias
    r = D.guardar_en_git([str(cat)])
    assert r["estado"] == "error" and "index.lock" in r["error"]


# ------------------------------------------------------------------ pieza 2: el implementador y el reparto en marcha
def test_el_implementador_ignora_el_catalogo_sucio_solo_con_un_reparto_en_marcha(repo):
    from nucleo import candado, puerta
    cat = repo / "documentacion" / "CATALOGO_HERRAMIENTAS.md"
    cat.write_text(cat.read_text(encoding="utf-8") + "- a medias\n", encoding="utf-8")
    assert not D.reparto_en_marcha() and not puerta.arbol_limpio(repo)
    with candado.exclusivo(D.ALMACEN.with_suffix(".lock"), espera_maxima=1, motivo="test"):
        assert D.reparto_en_marcha() and puerta.arbol_limpio(repo)
        (repo / "nucleo" / "cola.py").write_text("x = 9\n", encoding="utf-8")
        assert not puerta.arbol_limpio(repo)                                    # otra ruta sucia sigue bloqueando
    assert not D.reparto_en_marcha()


def test_ocupado_no_toma_el_candado(tmp_path):
    from nucleo import candado
    ruta = tmp_path / "x.lock"
    assert not candado.ocupado(ruta) and not ruta.exists()
    with candado.exclusivo(ruta, espera_maxima=1):
        assert candado.ocupado(ruta)
    assert not candado.ocupado(ruta)
    with candado.exclusivo(ruta, espera_maxima=1):                              # ocupado() no lo dejo tomado
        pass
