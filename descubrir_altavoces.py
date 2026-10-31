"""Tarea 7, primer paso: ¿ve el PC al Google Home mini?

A proposito NO usa pychromecast. Instalarlo es ambar (pip install) y
la cola dice que lo primero es comprobar si el altavoz es visible; si
no lo es, se para ahi. Instalar una libreria para descubrir que no
hay nada que descubrir es hacerlo al reves.

Asi que esto habla mDNS a pelo, con sockets de la biblioteca
estandar. Es el mismo protocolo que usa pychromecast por debajo:
se pregunta por _googlecast._tcp.local al grupo multicast
224.0.0.251:5353 y se escucha quien contesta.

Sale un informe por pantalla y en registros/altavoces.txt.
"""

from __future__ import annotations

import socket
import struct
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

SALIDA = RAIZ / "registros" / "altavoces.txt"
SALIDA.parent.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


GRUPO = "224.0.0.251"
PUERTO = 5353

SERVICIOS = [
    "_googlecast._tcp.local",   # Chromecast, Google Home, Nest
    "_spotify-connect._tcp.local",
    "_airplay._tcp.local",
]


def codificar_nombre(nombre: str) -> bytes:
    partes = [p.encode("ascii") for p in nombre.split(".") if p]

    return b"".join(bytes([len(p)]) + p for p in partes) + b"\x00"


def consulta(nombre: str) -> bytes:
    cabecera = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)

    # QTYPE 12 = PTR, QCLASS 1 = IN
    return cabecera + codificar_nombre(nombre) + struct.pack(">HH", 12, 1)


def leer_nombre(datos: bytes, pos: int) -> tuple[str, int]:
    """Lee un nombre DNS, siguiendo punteros de compresion."""

    partes: list[str] = []
    saltado = False
    fin = pos
    vueltas = 0

    while True:
        vueltas += 1

        if vueltas > 128 or pos >= len(datos):
            break

        largo = datos[pos]

        if largo == 0:
            pos += 1

            if not saltado:
                fin = pos

            break

        if largo & 0xC0 == 0xC0:
            if pos + 1 >= len(datos):
                break

            puntero = struct.unpack(">H", datos[pos:pos + 2])[0] & 0x3FFF

            if not saltado:
                fin = pos + 2
                saltado = True

            pos = puntero

            continue

        pos += 1

        partes.append(datos[pos:pos + largo].decode("utf-8", "replace"))

        pos += largo

    return ".".join(partes), fin


def analizar(datos: bytes, origen: str, hallazgos: dict) -> None:
    if len(datos) < 12:
        return

    _, _, n_preg, n_resp, n_aut, n_ext = struct.unpack(">HHHHHH", datos[:12])

    pos = 12

    for _ in range(n_preg):
        _, pos = leer_nombre(datos, pos)
        pos += 4

    for _ in range(n_resp + n_aut + n_ext):
        if pos >= len(datos):
            return

        nombre, pos = leer_nombre(datos, pos)

        if pos + 10 > len(datos):
            return

        tipo, _clase, _ttl, largo = struct.unpack(">HHIH", datos[pos:pos + 10])

        pos += 10

        cuerpo = datos[pos:pos + largo]

        ficha = hallazgos.setdefault(origen, {
            "ip": origen, "nombres": set(), "servicios": set(),
            "textos": set(), "puertos": set(), "anfitrion": "",
        })

        if tipo == 12:      # PTR
            destino, _ = leer_nombre(datos, pos)
            ficha["nombres"].add(destino)
            ficha["servicios"].add(nombre)

        elif tipo == 33:    # SRV
            if largo >= 6:
                _, _, puerto = struct.unpack(">HHH", cuerpo[:6])
                ficha["puertos"].add(puerto)
                anfitrion, _ = leer_nombre(datos, pos + 6)
                ficha["anfitrion"] = anfitrion

        elif tipo == 16:    # TXT
            i = 0
            while i < len(cuerpo):
                n = cuerpo[i]
                trozo = cuerpo[i + 1:i + 1 + n].decode("utf-8", "replace")
                if trozo:
                    ficha["textos"].add(trozo)
                i += 1 + n

        elif tipo == 1 and largo == 4:   # A
            ficha["ip"] = ".".join(str(b) for b in cuerpo)

        pos += largo


def ips_locales() -> list[str]:
    """Todas las IPv4 de este equipo, para preguntar por cada tarjeta."""

    encontradas = []

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]

            if ip not in encontradas and not ip.startswith("127."):
                encontradas.append(ip)
    except socket.gaierror:
        pass

    return encontradas or ["0.0.0.0"]


def barrer(segundos: float = 6.0) -> dict:
    hallazgos: dict = {}

    sockets = []

    for ip in ips_locales():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

            try:
                s.setsockopt(
                    socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                    socket.inet_aton(ip),
                )
            except OSError:
                pass

            s.bind((ip, 0))
            s.settimeout(0.4)

            sockets.append((ip, s))

        except OSError as e:
            anotar(f"  (no puedo usar la tarjeta {ip}: {e})")

    if not sockets:
        anotar("  No he podido abrir ningun socket. Nada que hacer.")
        return hallazgos

    for ip, s in sockets:
        anotar(f"  preguntando desde {ip}")

        for servicio in SERVICIOS:
            try:
                s.sendto(consulta(servicio), (GRUPO, PUERTO))
            except OSError as e:
                anotar(f"    fallo al enviar ({servicio}): {e}")

    limite = time.time() + segundos

    while time.time() < limite:
        for _, s in sockets:
            try:
                datos, remitente = s.recvfrom(9000)
                analizar(datos, remitente[0], hallazgos)
            except socket.timeout:
                continue
            except OSError:
                continue

    for _, s in sockets:
        s.close()

    return hallazgos


anotar(f"BUSQUEDA DE ALTAVOCES EN LA RED   {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 62)
anotar()
anotar("Protocolo: mDNS (el mismo que usa pychromecast por debajo).")
anotar("Sin instalar nada: solo la biblioteca estandar.")
anotar()

hallazgos = barrer(8.0)

anotar()
anotar("-" * 62)

if not hallazgos:
    anotar()
    anotar("RESULTADO: NO se ha visto ningun dispositivo.")
    anotar()
    anotar("Eso puede significar tres cosas distintas, y no son lo mismo:")
    anotar("  1. El altavoz esta apagado o desenchufado.")
    anotar("  2. El PC y el altavoz no estan en la misma red (tipico si el")
    anotar("     PC va por cable y el altavoz por wifi, o si hay wifi de")
    anotar("     invitados por medio).")
    anotar("  3. El cortafuegos de Windows bloquea el UDP 5353 entrante.")
    anotar()
    anotar("La tarea decia: si no es visible, parar aqui y preguntar. Eso")
    anotar("hago. No instalo pychromecast ni toco el cortafuegos.")
else:
    cast = []

    for ficha in hallazgos.values():
        todo = " ".join(ficha["servicios"]) + " " + " ".join(ficha["nombres"])

        if "googlecast" in todo:
            cast.append(ficha)

    anotar()
    anotar(f"RESULTADO: {len(hallazgos)} dispositivo(s) visible(s), "
           f"{len(cast)} de ellos compatibles con Cast.")

    for ficha in hallazgos.values():
        anotar()
        anotar(f"  IP        : {ficha['ip']}")

        if ficha["anfitrion"]:
            anotar(f"  Anfitrion : {ficha['anfitrion']}")

        if ficha["puertos"]:
            anotar(f"  Puertos   : {sorted(ficha['puertos'])}")

        for n in sorted(ficha["nombres"])[:4]:
            anotar(f"  Nombre    : {n}")

        # Lo interesante del TXT de un Chromecast: md (modelo) y fn
        # (nombre que le puso Damian).
        for t in sorted(ficha["textos"]):
            if t[:3] in ("md=", "fn=", "rs=", "ve="):
                anotar(f"  TXT       : {t}")

    if cast:
        anotar()
        anotar("SIGUIENTE PASO (necesita su visto bueno):")
        anotar("  Mandarle audio requiere pychromecast, y 'pip install' es")
        anotar("  ambar. La parte de descubrir ya esta hecha y funciona sin")
        anotar("  instalar nada, asi que la pregunta es solo si autoriza la")
        anotar("  instalacion.")

anotar()
anotar("FIN")
