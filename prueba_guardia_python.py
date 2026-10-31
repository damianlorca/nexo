# -*- coding: utf-8 -*-
"""Prueba nucleo/guardia_python.py (T091). Crea scripts de prueba en
registros/guardia_pruebas/ y los ejecuta a traves del lanzador."""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
D = RAIZ / "registros" / "guardia_pruebas"
D.mkdir(parents=True, exist_ok=True)
FUERA = RAIZ.parent / "guardia_fuera_de_zona.txt"  # Desktop\AI: fuera de la zona verde
LANZADOR = RAIZ / "nucleo" / "guardia_python.py"

CASOS = [
    # (nombre, codigo, debe_pasar, texto_esperado_en_salida)
    ("escribir_dentro", f"open(r'{D / 'ok.txt'}', 'w').write('x'); print('ESCRITO')", True, "ESCRITO"),
    ("escribir_fuera", f"open(r'{FUERA}', 'w').write('x')", False, "fuera de la zona verde"),
    ("pathlib_fuera", f"from pathlib import Path; Path(r'{FUERA}').write_text('x')", False, "fuera de la zona verde"),
    ("leer_secretos_directo", f"print(open(r'{RAIZ / 'secretos.toml'}').read()[:1])", False, "archivo rojo"),
    ("config_valor_permitido", "from nucleo.config import valor; print('LEIDO', bool(valor('canal.token_telegram')))", True, "LEIDO True"),
    ("borrar_fuera", f"import os; os.remove(r'{FUERA}')", False, "borrar fuera"),
    ("mover_a_fuera", f"import os; os.rename(r'{D / 'ok.txt'}', r'{FUERA}')", False, "mover (destino)"),
    ("escribir_blindado", f"open(r'{RAIZ / 'nucleo' / 'permisos.py'}', 'a')", False, "blindado"),
    ("subproceso_verde", "import subprocess, sys; r = subprocess.run([sys.executable, '-c', 'print(7*6)'], capture_output=True, text=True); print('HIJO', r.stdout.strip())", True, "HIJO 42"),
    ("subproceso_ambar", "import subprocess; subprocess.run(['winget', '--version'])", False, "comando no verde"),
    ("subproceso_rojo", "import subprocess; subprocess.run(['powershell', '-Command', 'Remove-Item x'])", False, "comando no verde"),
    ("os_system_rojo", "import os; os.system('del x.txt')", False, "comando no verde"),
    ("temp_permitido", "import tempfile; f = tempfile.NamedTemporaryFile('w', delete=False); f.write('x'); f.close(); print('TEMP OK')", True, "TEMP OK"),
    ("registro_windows", "import winreg; winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\\NexoPruebaGuardia')", False, "registro de Windows"),
    ("excepcion_capturada_no_escribe", f"\ntry:\n    open(r'{FUERA}', 'w').write('x')\nexcept Exception:\n    pass\nprint('SIGUE')", True, "SIGUE"),
    # el vault ya es zona verde (23/09): se prueba con una ruta de verdad fuera
    ("escritura_atomica_fuera_no_se_cuelga", f"from pathlib import Path; from nucleo.escritura import escribir_atomico; escribir_atomico(Path(r'{FUERA}'), 'x')", False, "GuardiaBloqueo"),
    ("devnull_permitido", "import subprocess, sys, platform; print('SO', platform.system()); subprocess.run([sys.executable, '-c', '1'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)", True, "SO Windows"),
    ("argv_y_main", "import sys; print('ARGV', sys.argv[1:], __name__)", True, "ARGV ['a', 'b'] __main__"),
]

ok, mal = 0, []
for nombre, codigo, debe_pasar, esperado in CASOS:
    s = D / f"caso_{nombre}.py"
    s.write_text(codigo, encoding="utf-8")
    args = [sys.executable, str(LANZADOR), str(s)] + (["a", "b"] if nombre == "argv_y_main" else [])
    try:
        r = subprocess.run(args, cwd=RAIZ, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        mal.append(nombre); print('MAL', nombre, 'TIMEOUT (bucle?)'); continue
    salida = r.stdout + r.stderr
    paso = r.returncode == 0
    bien = (paso == debe_pasar) and (esperado in salida) and not FUERA.exists()
    if bien:
        ok += 1
    else:
        mal.append(nombre)
    print("OK " if bien else "MAL", nombre, "| rc", r.returncode, "|", salida.strip().splitlines()[-1][:150] if salida.strip() else "")

if FUERA.exists():
    print("PELIGRO: se creo", FUERA)
print(f"\n{ok}/{len(CASOS)} OK", "" if not mal else f"fallan: {mal}")
raise SystemExit(1 if mal else 0)
