"""Candado de archivo: que dos procesos no se coman los cambios del otro.

Por que existe esto
--------------------
memoria/tareas.json lo tocan ahora VARIOS PROCESOS a la vez: un turno
de Claude corriendo `nucleo.tareas` por la CLI, el bot de Telegram
(/tarea, /hecha), y cualquier script suelto que llame a anadir() o
actualizar(). Cada uno de esos hace cargar() -> modificar -> guardar(),
y eso NO es atomico entre procesos distintos: si A y B leen el archivo
antes de que ninguno escriba, el que escriba segundo se come los
cambios del primero en silencio. Es la misma familia de fallo que ya
se vio y se anoto en T026 para memoria/estado.json, aplicada ahora a
memoria/tareas.json.

`nucleo.escritura.escribir_atomico` NO evita esto: garantiza que un
archivo no quede a medias, no que nadie escriba encima de otro.

Un archivo de candado creado con O_CREAT | O_EXCL SI es atomico a
nivel de sistema de archivos (falla si ya existe), y funciona igual
en Windows y en Linux sin depender de ctypes ni de nada especifico
de la plataforma.

Candados huerfanos
------------------
Si un proceso muere con el candado puesto -y aqui eso ya ha pasado,
Claude Desktop mata el servidor MCP sin avisar y sin dar tiempo a
nadie a terminar (ver memoria/auditoria.md, hallazgo B1)- un candado
que nadie suelta bloquearia todo para siempre. Por eso un candado mas
viejo que UMBRAL_HUERFANO se da por abandonado y se roba en vez de
esperarlo.
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

# Ninguna operacion sobre tareas.json (leer+modificar+escribir un
# archivo de unos pocos KB) tarda ni de lejos esto. Si un candado
# lleva mas tiempo puesto, es que su dueno murio con el puesto.
UMBRAL_HUERFANO = 30.0


@contextmanager
def bloqueo(ruta_candado: str | Path, espera_maxima: float = 10.0):
    """Bloquea ruta_candado durante el bloque `with`. Reintenta con espera corta.

    Si no consigue el candado en espera_maxima segundos (algo muy raro:
    significaria contencion real y sostenida), SIGUE SIN CANDADO en vez
    de colgarse para siempre - el riesgo que esto evita es una perdida
    de actualizacion ocasional, no algo que merezca bloquear el trabajo
    entero si el candado mismo se ha atascado.
    """

    candado = Path(ruta_candado)
    candado.parent.mkdir(parents=True, exist_ok=True)

    inicio = time.time()
    conseguido = False

    # PID + sufijo unico: al soltar solo se borra el candado si sigue
    # siendo ESTE (B4 de N02). Solo el PID no basta: dos hilos del mismo
    # proceso lo compartirian.
    firma = f"{os.getpid()}:{uuid.uuid4().hex}"

    while time.time() - inicio < espera_maxima:
        try:
            fd = os.open(str(candado), os.O_CREAT | os.O_EXCL | os.O_WRONLY)

            try:
                os.write(fd, firma.encode())
            finally:
                os.close(fd)

            conseguido = True

            break

        except (FileExistsError, PermissionError):
            # En Windows, el hueco entre que un hilo hace unlink() y
            # otro intenta crear el mismo nombre puede devolver
            # PermissionError en vez de FileExistsError (el borrado
            # de NTFS no es instantaneo). Se trata igual: es
            # contencion, no un permiso realmente denegado.
            try:
                edad = time.time() - candado.stat().st_mtime
            except OSError:
                edad = 0.0  # lo soltaron justo entre el intento y el stat

            if edad > UMBRAL_HUERFANO:
                try:
                    candado.unlink()
                except OSError:
                    pass

                continue

            time.sleep(0.05)

    if not conseguido:
        yield
        return

    try:
        yield
    finally:
        # Si el bloque tardo mas que UMBRAL_HUERFANO, otro proceso pudo
        # robar el candado: borrarlo entonces dejaria entrar a un tercero
        # a la vez que el ladron. Solo se suelta el propio.
        try:
            if candado.read_text() == firma:
                candado.unlink()
        except OSError:
            pass


class Ocupado(RuntimeError):
    """El recurso exclusivo lo tiene otro proceso y no se libero a tiempo."""


def _bloquear_so(fd: int) -> bool:
    """Candado del sistema operativo sobre el primer byte, sin esperar. True si se consiguio."""

    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _soltar_so(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def quien_tiene(ruta_candado: str | Path) -> str:
    """Texto legible de quien tiene (o tuvo por ultima vez) el candado exclusivo."""

    try:
        return Path(str(ruta_candado) + ".quien").read_text(encoding="utf-8").strip()
    except OSError:
        return "desconocido"


def ocupado(ruta_candado: str | Path) -> bool:
    """True si alguien tiene AHORA el candado exclusivo de `ruta_candado` (T1069). No espera ni lo toma: si esta libre,
    lo suelta al momento. Sin el archivo, nadie lo ha tomado nunca."""

    ruta = Path(ruta_candado)
    try:
        fd = os.open(str(ruta), os.O_RDWR)
    except OSError:
        return False
    try:
        if os.fstat(fd).st_size == 0:
            return False
        if _bloquear_so(fd):
            _soltar_so(fd)
            return False
        return True
    finally:
        os.close(fd)


@contextmanager
def exclusivo(ruta_candado: str | Path, espera_maxima: float = 600.0, motivo: str = ""):
    """Recurso exclusivo entre procesos (T193: el Chrome de NEXO), para bloques LARGOS.

    Distinto de bloqueo(): aquel es para escrituras de milisegundos y, si no consigue el
    candado, sigue sin el. Aqui dos procesos a la vez es justo el fallo que se evita, asi
    que el segundo ESPERA y, si se agota espera_maxima, lanza Ocupado con quien lo tiene.

    Usa el candado del sistema operativo (msvcrt en Windows, flock en Linux): si el
    proceso muere, el sistema lo suelta solo, sin umbral de huerfano ni robos. Tambien
    excluye a otro hilo del mismo proceso (en Windows el candado va por descriptor).
    """

    ruta = Path(ruta_candado)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(ruta), os.O_RDWR | os.O_CREAT)

    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")  # msvcrt necesita un byte que bloquear
        limite = time.time() + espera_maxima

        while not _bloquear_so(fd):
            if time.time() >= limite:
                raise Ocupado(f"ocupado por {quien_tiene(ruta)}; espere {espera_maxima:.0f} s")
            time.sleep(0.5)

        try:
            Path(str(ruta) + ".quien").write_text(
                f"pid {os.getpid()} desde {time.strftime('%H:%M:%S')} ({motivo or 'sin motivo'})",
                encoding="utf-8")
        except OSError:
            pass

        try:
            yield
        finally:
            _soltar_so(fd)
    finally:
        os.close(fd)
