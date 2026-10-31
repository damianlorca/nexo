# -*- coding: utf-8 -*-
"""Prueba de roles/ (sin llamar a ningun modelo: cero RAM, cero coste)."""
import roles

fallos = []


def comprobar(cond, msg):
    if not cond:
        fallos.append(msg)


# 1. Los roles cargan y son cortos (presupuesto de prefill en CPU).
# revisor_borrador lo usa nucleo/trabajo.py (revision de borradores web); se anadio despues.
for nombre in ("revisor", "revisor_borrador", "verificador", "codigo"):
    t = roles.cargar(nombre)
    comprobar(len(t) > 200, f"{nombre}: demasiado corto")
    comprobar(len(t) < 2000, f"{nombre}: {len(t)} car., pasa de 2000 (≈500 tok)")

comprobar(roles.listar() == ["codigo", "revisor", "revisor_borrador", "verificador"], f"listar: {roles.listar()}")

try:
    roles.cargar("no_existe")
    fallos.append("cargar rol inexistente no lanzo KeyError")
except KeyError:
    pass

# 2. Veredictos del revisor.
comprobar(roles.veredicto("revisor", "SUGERENCIA | a.py:3 | x | y\nVEREDICTO: APROBADO") == "APROBADO", "revisor aprobado")
comprobar(roles.veredicto("revisor", "BLOQUEANTE | a.py:1 | x | y\nVEREDICTO: CAMBIOS_NECESARIOS") == "CAMBIOS_NECESARIOS", "revisor cambios")
comprobar(roles.veredicto("revisor", "todo bien, lo apruebo") is None, "revisor sin linea -> None")
comprobar(roles.veredicto("revisor", "VEREDICTO: PERFECTO") is None, "revisor veredicto invalido -> None")
# Cita el formato primero y luego responde: manda la ultima.
comprobar(
    roles.veredicto("revisor", "Formato: VEREDICTO: APROBADO\n...\nVEREDICTO: APROBADO\nBLOQUEANTE | b.py:9 | z | w\nVEREDICTO: CAMBIOS_NECESARIOS")
    == "CAMBIOS_NECESARIOS",
    "revisor: debe mandar la ultima linea",
)

# 3. Verificador: un veredicto de otro rol no vale.
comprobar(roles.veredicto("verificador", "x | ninguna | FALTA\nVEREDICTO: NO_VERIFICADO") == "NO_VERIFICADO", "verif no")
comprobar(roles.veredicto("verificador", "VEREDICTO: APROBADO") is None, "verif no acepta APROBADO")

# 3b. Veredicto deducido del verificador (banco T100 v2).
cab = 'AFIRMACION | evidencia que la respalda (o "ninguna") | OK o FALTA\n'
comprobar(roles.veredicto_verificador(cab + "x | salida real | OK\ny | test | OK") == ("VERIFICADO", "deducido"), "deducido todo OK")
comprobar(roles.veredicto_verificador(cab + "x | salida real | OK\ny | ninguna | FALTA") == ("NO_VERIFICADO", "deducido"), "deducido alguna FALTA")
comprobar(roles.veredicto_verificador("x | ninguna | FALTA\nVEREDICTO: INSUFICIENTE") == ("INSUFICIENTE", "explicito"), "manda el explicito")
comprobar(roles.veredicto_verificador(cab) == (None, "ninguno"), "solo cabecera -> ninguno")
comprobar(roles.veredicto_verificador("parece que funciona") == (None, "ninguno"), "texto libre -> ninguno")

# 4. Codigo (formato CODIGO / FIN_CODIGO + diff mecanico).
ORIG = "def ultimos(lista, n):\n    return lista[-n + 1:]\n\ndef primero(lista):\n    return lista[0]"
CORR = ORIG.replace("[-n + 1:]", "[-n:]")
bueno = "CODIGO\n" + CORR + "\nFIN_CODIGO\nFUERA_DE_ALCANCE: ninguna\nINTERPRETACION: no ambigua"
c = roles.campos_codigo(bueno)
comprobar(c["ok"] and c["codigo"] == CORR, f"codigo bueno: {c}")
comprobar(roles.lineas_cambiadas(ORIG, c["codigo"]) == 1, "una linea cambiada")
con_fence = bueno.replace("CODIGO\n", "CODIGO\n```python\n").replace("\nFIN_CODIGO", "\n```\nFIN_CODIGO")
comprobar(roles.campos_codigo(con_fence)["codigo"] == CORR, "quita las vallas ```")
comprobar(roles.lineas_cambiadas(ORIG, ORIG) == 0, "sin cambios -> 0")
solo_valla = "```python\n" + CORR + "\nFIN_CODIGO\nFUERA_DE_ALCANCE: ninguna\nINTERPRETACION: no ambigua\n```"
comprobar(roles.campos_codigo(solo_valla)["codigo"] == CORR, "valla como apertura")
comprobar(roles.campos_codigo("```python\n" + CORR + "\n```")["codigo"] is None, "sin FIN_CODIGO no vale")
comprobar(roles.lineas_cambiadas(ORIG, CORR.replace("lista[0]", "lista[0] if lista else None")) == 2, "cambio de mas cuenta")
comprobar(not roles.campos_codigo("he cambiado la linea 1")["ok"], "codigo sin bloque")
comprobar(not roles.campos_codigo(bueno.replace("FUERA_DE_ALCANCE: ninguna\n", ""))["ok"], "codigo sin FUERA")

if fallos:
    print("FALLOS:")
    for f in fallos:
        print(" -", f)
    raise SystemExit(1)

print("TODO VALE:", ", ".join(f"{n}={len(roles.cargar(n))} car." for n in roles.listar()))
