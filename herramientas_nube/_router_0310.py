import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T
T.anotar("T665", ("03/10 Damian: el router sin usar es Arcadyan PRV3399B-B-LT (router de operadora). Investigar en T665 "
                  "si su firmware permite usarlo como punto de acceso, switch de puertos Ethernet o red aparte para el "
                  "servidor; si no aporta, descartarlo con motivo."))
print("ok")
