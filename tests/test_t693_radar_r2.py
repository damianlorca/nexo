# -*- coding: utf-8 -*-
"""T693 R2: nota local del radar (perfil privado leido en el PC) y fuentes de Damian con sus terminos."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from types import SimpleNamespace

from nucleo import radar as R
from nucleo import radar_nota as N

PERFIL = """# Perfil
## Datos basicos
- Nombre: Persona Secreta, DNI 00000000X
### Que buscar
- Practicas
### Empresas y organizaciones que mas le interesan (punto de partida)
- IA y tecnologia top: Anthropic (programas de estudiantes), OpenAI, Google, NVIDIA.
- Encajan con su perfil (anadido por el coordinador): agencias y centros como ESA y CERN (programas de estudiantes).
### Fuentes
- https://ej.org
"""

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>CERN Research Fellowship 2027</title><link>https://ej.org/cern</link><description>engineering</description></item>
<item><title>Legal internship in Geneva</title><link>https://ej.org/legal</link></item>
<item><title>Free online course on marketing</title><link>https://ej.org/mooc</link><description>internship prep</description></item>
</channel></rss>"""


def _perfil(tmp_path):
    ruta = tmp_path / "perfil.md"
    ruta.write_text(PERFIL, encoding="utf-8")
    return ruta


def test_empresas_solo_de_su_seccion_y_sin_datos_personales(tmp_path):
    e = N.empresas_del_perfil(_perfil(tmp_path))
    assert e == ["Anthropic", "OpenAI", "Google", "NVIDIA", "ESA", "CERN"]
    assert N.empresas_del_perfil(tmp_path / "no_existe.md") == []


def test_nota_determinista_con_empresa_palabras_y_castigo():
    si, no, emp = ["internship", "internships", "fellowship", "engineering"], ["online course"], ["CERN"]
    assert N.puntuar({"titulo": "CERN Research Fellowship", "texto": "engineering"}, si, no, emp) == \
        (85, "organización que te interesa: CERN; encaja con lo que buscas: fellowship, engineering")
    assert N.puntuar({"titulo": "Paid internships and internship"}, si, no, emp)[0] == 45   # plural cuenta una vez
    nota, motivo = N.puntuar({"titulo": "Free online course", "texto": "internship"}, si, no, emp)
    assert nota == 0 and "pero parece online course" in motivo
    assert N.puntuar({"titulo": "Cernicalo"}, si, no, emp)[0] == 30          # palabra entera, no trozos


def test_pasada_real_publica_por_nota_y_el_perfil_no_sale(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(N, "PERFIL", _perfil(tmp_path))
    cfg = {"id": "oport", "modo": "real", "por_dia": 5, "umbral": 45, "nota": {"perfil": True},
           "filtros": {"palabras_si": ["internship", "fellowship", "engineering"], "palabras_no": ["online course"]},
           "fuentes": [{"id": "feed", "tipo": "rss", "url": "u", "terminos": "RSS oficial"}]}
    R.carpeta("oport").mkdir(parents=True)
    (R.carpeta("oport") / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    vacio = SimpleNamespace(text="<rss><channel></channel></rss>", raise_for_status=lambda: None)
    lleno = SimpleNamespace(text=RSS, raise_for_status=lambda: None)
    R.pasada("oport", datetime(2026, 10, 5), get=lambda *a: vacio)          # linea base vacia
    with caplog.at_level(logging.DEBUG):
        inf = R.pasada("oport", datetime(2026, 10, 6), get=lambda *a: lleno)
    assert [(a["titulo"], a["nota"]) for a in inf["publicadas"]] == [("CERN Research Fellowship 2027", 85),
                                                                     ("Legal internship in Geneva", 45)]
    guardado = (R.carpeta("oport") / "articulos.jsonl").read_text(encoding="utf-8")
    for privado in ("Persona Secreta", "00000000X", "Anthropic"):
        assert privado not in guardado and privado not in caplog.text and privado not in json.dumps(inf)


def test_config_real_de_oportunidades_tiene_terminos_y_linktree_apagada():
    """El config versionado: cada fuente activa con sus terminos comprobados; Linktree no se lee (robots.txt)."""
    from pathlib import Path
    ruta = Path(__file__).resolve().parent.parent / "memoria" / "radares" / "oportunidades" / "config.json"
    cfg = json.loads(ruta.read_text(encoding="utf-8"))
    estado = {f["id"]: R.fuente_lista(f) for f in cfg["fuentes"]}
    assert estado["opportunitiesradar"] is None and estado["opportunitiescircle"] is None
    assert "robots.txt" in estado["linktree_opportunity4u"]
    assert cfg["modo"] == "simular" and cfg["nota"] == {"perfil": True}
