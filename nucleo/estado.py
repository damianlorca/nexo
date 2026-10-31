"""Estado persistente de la mision en curso.

Que se pidio, por donde va, que ha fallado. Sobrevive a reinicios
para que una sesion nueva pueda retomar sin empezar de cero.

Este archivo es lo mas valioso del proyecto: es la unica memoria
que une un turno de noche con el siguiente. Por eso se guarda de
forma atomica y por eso, si alguna vez aparece roto, NO se pisa en
silencio. Ver hallazgos D1, D2 y D3 de memoria/auditoria.md.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico


ARCHIVO = RAIZ / "memoria" / "estado.json"

# Candado para los cambios MECANICOS de mas abajo (actualizar_campos,
# anadir_hecho): distinto del problema que resuelve la clase Estado
# (corrupcion). Ver el docstring de actualizar_campos().
CANDADO = RAIZ / "memoria" / ".candado_estado.lock"


@dataclass
class Estado:
    mision: str = ""
    estado: str = "inactivo"        # inactivo | trabajando | esperando | hecho | fallo
    paso: int = 0
    errores: int = 0
    esperando_a: str = ""           # que pregunta esta pendiente de respuesta
    ultima_accion: str = ""
    ultimo_resultado: str = ""
    actualizado: str = ""
    siguiente_turno: list[str] = field(default_factory=list)
    hechos: list[str] = field(default_factory=list)

    def guardar(self) -> None:
        self.actualizado = time.strftime("%Y-%m-%d %H:%M:%S")

        escribir_atomico(
            ARCHIVO,
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
        )

    def anotar(self, accion: str, resultado: str) -> None:
        self.paso += 1
        self.ultima_accion = accion
        self.ultimo_resultado = resultado[:2000]

        self.guardar()


def _apartar_roto(archivo: Path) -> Path | None:
    """Guarda el estado ilegible en vez de pisarlo. Nunca se borra."""

    if not archivo.is_file():
        return None

    destino = RAIZ / "_archivo" / time.strftime("%Y%m%d")

    try:
        destino.mkdir(parents=True, exist_ok=True)

        roto = destino / f"estado_roto_{time.strftime('%H%M%S')}.json"

        archivo.replace(roto)

        return roto

    except OSError:
        return None


def _ultimo_respaldo() -> Path | None:
    """El respaldo de estado.json mas reciente que haya en _respaldos/."""

    base = RAIZ / "_respaldos"

    if not base.is_dir():
        return None

    candidatos = sorted(
        base.glob("*/*estado_*.json"),   # tambien memoria__estado_*.json
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return candidatos[0] if candidatos else None


def _desde_datos(datos: dict) -> tuple[Estado, list[str]]:
    """Construye un Estado quedandose solo con los campos conocidos.

    Devuelve tambien los campos que se han tenido que descartar, para
    que quien llame pueda quejarse en vez de perderlos en silencio.
    """

    permitidos = {f for f in Estado.__dataclass_fields__}

    descartados = sorted(k for k in datos if k not in permitidos)

    return Estado(**{k: v for k, v in datos.items() if k in permitidos}), descartados


def cargar() -> Estado:
    """Lee el estado del disco.

    Si el archivo esta roto no devuelve un estado en blanco y a
    correr: aparta el roto, intenta recuperar el ultimo respaldo y
    deja dicho en el propio estado que ha pasado algo. Un estado en
    blanco devuelto en silencio se guarda encima del bueno al primer
    guardar() y se pierde la memoria entera.
    """

    if not ARCHIVO.is_file():
        return Estado()

    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))

    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        return _recuperar(f"{type(e).__name__}: {e}")

    if not isinstance(datos, dict):
        return _recuperar(f"el archivo no contiene un objeto JSON sino {type(datos).__name__}")

    estado, descartados = _desde_datos(datos)

    if descartados:
        estado.hechos.append(
            "[aviso] Al cargar el estado se descartaron campos que no existen "
            f"en la clase Estado: {', '.join(descartados)}. Se han PERDIDO. "
            "Si hacen falta, hay que anadirlos a nucleo/estado.py."
        )

    return estado


def _recuperar(motivo: str) -> Estado:
    """El estado no se puede leer. Aparta, recupera lo que se pueda y avisa."""

    roto = _apartar_roto(ARCHIVO)

    respaldo = _ultimo_respaldo()

    if respaldo is not None:
        try:
            datos = json.loads(respaldo.read_text(encoding="utf-8"))

            if isinstance(datos, dict):
                estado, _ = _desde_datos(datos)

                estado.errores += 1
                estado.estado = "fallo"
                estado.ultimo_resultado = (
                    f"ESTADO RECUPERADO DE RESPALDO. El estado.json estaba "
                    f"ilegible ({motivo}). El roto esta en "
                    f"{roto if roto else 'no se pudo apartar'}. Lo que lees "
                    f"viene de {respaldo.name}, o sea que puede faltar lo "
                    "ultimo del turno anterior. Revisa antes de fiarte."
                )

                return estado

        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass

    vacio = Estado()

    vacio.errores = 1
    vacio.estado = "fallo"
    vacio.ultimo_resultado = (
        f"ESTADO PERDIDO. estado.json estaba ilegible ({motivo}) y no habia "
        f"ningun respaldo utilizable. El archivo roto esta en "
        f"{roto if roto else 'no se pudo apartar'}: NO lo borres, puede que "
        "se pueda leer a mano. Se empieza de cero."
    )

    return vacio


# ------------------------------------------------- cambios mecanicos (T035)
#
# cargar()/guardar()/anotar() de arriba resuelven la CORRUPCION (D1-D3):
# si el archivo aparece roto, no se pisa en silencio. Pero no resuelven
# la CONCURRENCIA: dos procesos que hacen cargar() -> modificar el
# objeto en Python -> guardar() pueden pisarse igual que ya paso con
# tareas.json (T026, T031). Un turno de Claude que hace esto a mano con
# leer()+escribir() (dos llamadas de herramienta separadas, con todo
# el pensar del turno en medio) NO se puede proteger con un candado -
# el hueco dura minutos, no milisegundos. Eso sigue siendo asi y sigue
# necesitando "releer antes de escribir, fundir no reemplazar".
#
# Lo que SI se puede proteger es un cambio MECANICO que cabe entero en
# una sola llamada de Python (por ejemplo desde ejecutar_python, o
# desde codigo que ya corre en el equipo como el bot): cargar, cambiar
# un campo suelto o anadir un hecho, guardar, todo bajo candado, sin
# que el turno tenga que reconstruir el JSON entero a mano. Estas dos
# funciones son eso: piezas nuevas, no tocan nada de lo de arriba.

_CAMPOS_MECANICOS = (
    "mision",
    "estado",
    "paso",
    "errores",
    "esperando_a",
    "ultima_accion",
    "ultimo_resultado",
)


def actualizar_campos(**campos) -> Estado:
    """Cambia SOLO los campos escalares indicados, bajo candado.

    No toca 'hechos' ni 'siguiente_turno' (para eso, anadir_hecho() o
    editar el objeto entero a mano): mezclar listas por aqui invitaria
    a perder entradas igual que se queria evitar.
    """

    desconocidos = set(campos) - set(_CAMPOS_MECANICOS)

    if desconocidos:
        raise ValueError(
            f"actualizar_campos() no toca estos campos: {sorted(desconocidos)}"
        )

    with bloqueo(CANDADO):
        estado = cargar()

        for clave, valor in campos.items():
            setattr(estado, clave, valor)

        estado.guardar()

    return estado


def anadir_hecho(texto: str) -> Estado:
    """Anade UNA linea a 'hechos', bajo candado, sin tocar el resto."""

    with bloqueo(CANDADO):
        estado = cargar()

        estado.hechos.append(texto.strip())

        estado.guardar()

    return estado
