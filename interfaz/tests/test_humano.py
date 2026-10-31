# -*- coding: utf-8 -*-
"""T230: Centro, Tareas y ficha en palabras normales, filtros en la URL y la capa tecnica plegada."""
from __future__ import annotations

from datetime import datetime

from interfaz import humano as H
from nucleo import tareas as T


# ---------------------------------------------------------------- traducciones
def test_fechas_relativas():
    ahora = datetime(2026, 9, 28, 12, 0, 0)
    assert H.hace("2026-09-28 11:58:00", ahora) == "hace 2 min"
    assert H.hace("2026-09-28 08:32:10", ahora) == "hoy a las 08:32"
    assert H.hace("2026-09-27 23:10:00", ahora) == "ayer a las 23:10"
    assert H.hace("2026-09-25 10:00:00", ahora) == "hace 3 días"
    assert H.hace("2026-08-01 10:00:00", ahora) == "el 01/08"
    assert H.hace(None, ahora) == "—" and H.hace("basura", ahora) == "—"


def test_etiquetas_separan_lo_humano_de_lo_tecnico():
    e = H.etiquetas(["cat:codigo", "prov:claude", "tema:interfaz_app_voz", "origen:damian_chat",
                     "de_borrador:T1_x.md", "tarea_origen:T001", "bug"])
    assert (e["categoria"], e["proveedor"], e["tema"], e["origen"]) == (
        "Programación", "Claude", "Web, app y voz", "Tú, hablando con Claude")
    assert e["tecnicas"] == ["de_borrador:T1_x.md", "tarea_origen:T001"] and e["otras"] == ["bug"]


def test_resumen_usa_el_propio_o_uno_provisional_del_detalle():
    t = {"detalle": "Damian 27/09: la web esta escrita para IAs. Hay que traducirla. Tercera frase.\n1) filtrar"}
    r = H.resumen(t)
    assert r == {"texto": "La web esta escrita para IAs. Hay que traducirla.", "provisional": True}
    assert H.resumen({**t, "resumen_humano": "Hecho por Qwen."}) == {"texto": "Hecho por Qwen.", "provisional": False}


def test_estados_en_palabras_normales():
    assert H.estado("HECHO SIN TESTEAR")["nombre"] == "Hecha, falta comprobarla"
    assert H.estado("PLANIFICADO")["grupo"] == "por_hacer"


def test_aviso_de_auditoria_dice_por_que_y_que_pasa_ahora():
    a = {"tarea": "T9", "titulo": "Investigar", "cuando": "2026-09-28 03:00:00", "resultado": "BLOQUEADA",
         "fallos": ["e_ok_absoluto"], "revisado": None, "borrador": "T9_x.md"}
    v = H.aviso_auditoria(a)
    assert not v["resuelto"] and "terminado y comprobado" in v["por_que"][0] and "Claude" in v["que_pasa"]
    v = H.aviso_auditoria({**a, "revisado": {"veredicto": "APROBADO", "motivo": "ok"}})
    assert v["resuelto"] and "dio por bueno" in v["que_pasa"]


def test_ias_con_estado_y_marca():
    assert H.ia("claude", "disponible") == {"clave": "claude", "nombre": "Claude", "letra": "C",
                                            "punto": "verde", "texto": "lista"}
    assert H.ia("groq", "enfriamiento")["punto"] == "ambar" and H.ia("qwen", "error")["punto"] == "rojo"
    assert H.ia("rara", "no_disponible")["clave"] == "otra"


# ---------------------------------------------------------------- pantallas
def test_boceto_redirige_a_las_pantallas_reales(cliente, csrf):
    for viejo, nuevo in (("/boceto", "/"), ("/boceto/centro", "/"), ("/boceto/tareas?quien=damian", "/tareas?depende=damian"),
                         ("/boceto/tareas/T005", "/tareas/T005")):
        r = cliente.get(viejo, follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == nuevo


def test_tareas_filtra_ordena_y_ensena_id_con_titulo(cliente, csrf):
    a = T.anadir("Revisar becas", depende="damian", importancia=5, urgencia=5, etiquetas=["cat:personal"])
    b = T.anadir("Programar cosa", etiquetas=["cat:codigo", "tema:interfaz_app_voz"])
    T.completar(b["id"], despues="nada: sin siguiente", cierre={"estado_real": "HECHO SIN TESTEAR", "evidencia": "cerrada en un test sin prueba"})
    r = cliente.get("/tareas").text
    assert "Revisar becas" in r and "Programar cosa" not in r          # pendientes por defecto
    assert "Te toca a ti" in r and f"{a['id']}</span> · Revisar becas" in r
    r = cliente.get("/tareas/lista", params={"estado": "sin_comprobar"}).text
    assert "Programar cosa" in r and "Revisar becas" not in r and "Hecha, falta comprobarla" in r
    r = cliente.get("/tareas/lista", params={"estado": "todas", "categoria": "Programación"})
    assert "Programar cosa" in r.text and "Revisar becas" not in r.text and "Quitar filtro Programación" in r.text
    assert r.headers["hx-replace-url"] == "/tareas?estado=todas&categoria=Programaci%C3%B3n"
    r = cliente.get("/tareas", params={"q": "becas", "orden": "creada"}).text
    assert "Revisar becas" in r and "Programar" not in r
    # Filtros desconocidos no rompen: se ignoran
    assert cliente.get("/tareas", params={"estado": "x", "orden": "y", "depende": "z", "tema": "w"}).status_code == 200


def test_orden_de_la_lista(cliente, csrf):
    T.anadir("vieja importante", importancia=5, urgencia=5)
    T.anadir("nueva sin prisa", importancia=1, urgencia=1)
    datos = T.cargar()
    datos["tareas"][0]["creada"] = "2026-01-01 10:00:00"   # la importante, mucho mas vieja
    T.guardar(datos)
    r = cliente.get("/tareas/lista").text
    assert r.index("vieja importante") < r.index("nueva sin prisa")
    r = cliente.get("/tareas/lista", params={"orden": "creada"}).text
    assert r.index("nueva sin prisa") < r.index("vieja importante")


def test_ficha_humana_con_detalle_tecnico_plegado(cliente, csrf):
    t = T.anadir("Mi tarea", detalle="Damian 27/09: esto es lo que hay que hacer. Y por que.",
                 etiquetas=["cat:codigo", "de_borrador:T5_x.md"])
    T.anotar(t["id"], "primera nota")
    r = cliente.get(f"/tareas/{t['id']}").text
    assert "Esto es lo que hay que hacer. Y por que." in r and "Resumen provisional" in r
    assert "Por hacer" in r and "primera nota" in r and f"{t['id']}</span> · Mi tarea" in r
    tecnico = r[r.index("Detalle técnico"):]
    assert "de_borrador:T5_x.md" in tecnico and "<code>" + t["id"] in tecnico
    assert "de_borrador" not in r[:r.index("Detalle técnico")]
    # Las acciones de siempre siguen en la ficha
    for accion in ("Añadir nota", "Marcar hecha", "Editar campos"):
        assert accion in r
    assert f'hx-get="/tareas/{t["id"]}/tecnico"' in r
    assert "de_borrador:T5_x.md" in cliente.get(f"/tareas/{t['id']}/tecnico").text


def test_relacionadas_con_id_y_titulo(cliente, csrf):
    madre = T.anadir("La madre")
    hija = T.anadir("La hija", etiquetas=[f"tarea_origen:{madre['id']}"])
    r = cliente.get(f"/tareas/{madre['id']}").text
    assert f"Ha generado: <a href=\"/tareas/{hija['id']}\">{hija['id']} · La hija</a>" in r
    r = cliente.get(f"/tareas/{hija['id']}").text
    assert f"{madre['id']} · La madre" in r


def test_centro_pone_arriba_lo_que_necesita_a_damian(cliente, csrf):
    T.anadir("Firmar papeles", depende="damian")
    r = cliente.get("/centro/resumen").text
    assert "Nexo funcionando" in r and "Necesita tu atención" in r and "Firmar papeles" in r
    assert r.index("Firmar papeles") < r.index("Lo último que se ha movido")
    pagina = cliente.get("/tecnico").text
    assert pagina.index('hx-get="/centro/resumen"') < pagina.index("<summary>Detalle técnico") < pagina.index('hx-get="/centro/revision"')


def test_centro_parado_y_vacio(cliente, csrf):
    from nucleo import parada
    r = cliente.get("/centro/resumen").text
    assert "Nada. Todo lo pendiente lo lleva Nexo." in r
    parada.activar("prueba de parada", "damian")
    assert "Nexo parado" in cliente.get("/centro/resumen").text


def test_panel_de_ias(cliente, csrf):
    r = cliente.get("/centro/ias").text
    assert "bc-punto-verde" in r and "Falso" in r and "lista" in r and "T195" in r


def test_paneles_nuevos_piden_sesion(cliente):
    for url in ("/centro/resumen", "/centro/ias", "/tareas/T001/tecnico"):
        assert cliente.get(url).status_code == 401


def test_aparcadas_salen_de_pendientes_y_dicen_cuando_vuelven(cliente, csrf):
    a = T.anadir("Tarea aparcada")
    T.actualizar(a["id"], estado="aparcada")
    datos = T.cargar()     # `aparcada_hasta` aun no existe en el core (actualizar lo ignoraria): a mano
    next(x for x in datos["tareas"] if x["id"] == a["id"])["aparcada_hasta"] = "2026-10-05"
    T.guardar(datos)
    T.anadir("Tarea normal")
    r = cliente.get("/tareas").text
    assert "Tarea normal" in r and "Tarea aparcada" not in r
    r = cliente.get("/tareas", params={"estado": "aparcadas"}).text
    assert "Tarea aparcada" in r and "vuelve el 05/10" in r and "Tarea normal" not in r
    r = cliente.get(f"/tareas/{a['id']}").text
    assert "vuelve el 05/10" in r


def test_centro_ignora_las_aparcadas(cliente, csrf):
    a = T.anadir("Firmar luego", depende="damian")
    T.actualizar(a["id"], estado="aparcada")
    r = cliente.get("/centro/resumen").text
    atencion = r[r.index("Necesita tu atención"):r.index("Lo último que se ha movido")]
    assert "Firmar luego" not in atencion and "Nada. Todo lo pendiente" in atencion


def test_mirar_no_escribe_nada(cliente, csrf):
    t = T.anadir("Intacta")
    antes = T.cargar()
    for u in ("/", "/centro/resumen", "/tareas", "/tareas/lista", f"/tareas/{t['id']}", f"/tareas/{t['id']}/tecnico"):
        cliente.get(u)
    assert T.cargar() == antes


def test_centro_te_toca_solo_lo_suyo_y_avisa_de_las_mal_asignadas(cliente, csrf):
    """Guardia de responsables (05/10): lo que no es de Damian no sale en "Te toca"; el repaso lo avisa."""
    from nucleo import responsables
    T.anadir("Firmar papeles", depende="damian")
    mala = T.anadir("Revisar logs del vigia", depende="ia")
    datos = T.cargar()
    next(t for t in datos["tareas"] if t["id"] == mala["id"])["depende"] = "damian"   # colada a mano en el JSON
    T.guardar(datos)
    responsables.repaso()
    r = cliente.get("/centro/resumen").text
    assert "Tareas a tu nombre que no son tuyas" in r and f'href="/tareas/{mala["id"]}"' in r
    te_toca = r[:r.index("Tareas a tu nombre")]
    assert "Firmar papeles" in te_toca and "Revisar logs del vigia" not in te_toca


def test_centro_dice_si_el_altavoz_no_se_ve(cliente, csrf, monkeypatch):
    from extremidades import altavoz
    o = altavoz.Oyente(buscar_=lambda: (None, None), contar_=lambda c: None, avisar_=lambda *a: None,
                       leer_=lambda: None, guardar_=lambda v: None, fuera_=lambda: True)
    o.conectar()
    monkeypatch.setattr(altavoz, "_oyente", o)
    assert "altavoz no visible (¿el PC está fuera de casa?)" in cliente.get("/centro/resumen").text
    monkeypatch.setattr(altavoz, "_oyente", None)
    assert "altavoz no visible" not in cliente.get("/centro/resumen").text
