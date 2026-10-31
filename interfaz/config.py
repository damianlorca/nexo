# -*- coding: utf-8 -*-
"""Ajustes de la interfaz web: rutas del repo, host, puerto y limites.

Un objeto `Ajustes` por app (crear_app lo recibe) para que los tests puedan
apuntar a una carpeta temporal sin tocar memoria/ de verdad.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"   # NUNCA 0.0.0.0 (SPEC: backend solo en localhost)
# 8765: puerto definitivo. La variable solo sirve para pruebas en otro puerto;
# tiene que coincidir con el --port de uvicorn (se usa para validar Host/Origin).
PUERTO = int(os.environ.get("NEXO_INTERFAZ_PUERTO", "8765"))
# /salud lo devuelve para que el vigia (interfaz/vigia.py) distinga esta web de otro programa en el puerto.
# Aqui y no en rutas/: el vigia lo importa sin cargar la web entera.
APP_ID = "nexo-interfaz"


@dataclass
class Ajustes:
    raiz: Path = RAIZ
    puerto: int = PUERTO
    # Token por arranque: lo lee interfaz/scripts/abrir_nexo.bat. En .gitignore. La variable
    # permite a una instancia de prueba no pisar (ni borrar al parar) el token de la de verdad.
    token_fichero: Path = Path(os.environ.get("NEXO_INTERFAZ_TOKEN_FICHERO", RAIZ / "memoria" / "interfaz_token.txt"))
    # Forzar Secure siempre. Sin forzar, va Secure solo si la peticion llega por Tailscale Serve
    # (HTTPS); en http://127.0.0.1 no puede (el navegador no la guardaria).
    cookie_secure: bool = False
    # Hito movil: nombre del PC en la tailnet y login del dueno (tailnet.py). None = solo local.
    # En produccion los rellena Ajustes.produccion(); los tests los ponen a mano.
    tailnet_host: str | None = None
    tailnet_dueno: str | None = None
    # True en produccion: app.py vuelve a preguntar a Tailscale en marcha (ver aplicar_tailnet).
    tailnet_auto: bool = False
    # Push: claves VAPID y suscripciones (push.py). En .gitignore: nunca al repo.
    push_carpeta: Path = RAIZ / "memoria" / "push"
    # Rate-limit de /entrar: como mucho N fallos por ventana (segundos).
    intentos_login: int = 5
    ventana_login: float = 60.0
    # Vigilancia de ficheros del core para el SSE (vigilancia.py).
    vigilar: bool = True
    intervalo_vigilancia: float = 1.0
    # T231: el planificador de turnos corre SOLO en la web definitiva (8765); una instancia de prueba en otro
    # puerto no lanza turnos (si no, dos webs se repartirian la cola).
    planificar: bool = PUERTO == 8765
    # T697: el oyente del altavoz "Damián" (extremidades/altavoz.py), igual: solo en la web definitiva y con la
    # vigilancia encendida (los tests la apagan). Se apaga tambien con altavoz.oyente = false en config.toml.
    altavoz: bool = PUERTO == 8765

    @classmethod
    def produccion(cls) -> "Ajustes":
        """Ajustes de la web de verdad: host y dueno de la tailnet los rellena app.refrescar_tailnet.

        NEXO_TAILNET_DUENO cambia el login aceptado (por defecto, el del propio PC)."""
        # Sin preguntar a Tailscale aqui: esto corre al IMPORTAR interfaz.app (tambien en los tests).
        # La primera pregunta la hace app.refrescar_tailnet nada mas arrancar, en un hilo.
        a = cls(tailnet_auto=True)
        a.aplicar_tailnet(None)   # solo NEXO_TAILNET_DUENO, si esta puesta
        return a

    def aplicar_tailnet(self, datos: dict | None) -> bool:
        """Pone host y dueno segun `tailnet.estado()`. Devuelve si algo cambio.

        Al iniciar sesion la web puede arrancar antes de que Tailscale tenga su usuario cargado
        (25/09: el movil recibia 401 hasta reiniciar la web); por eso app.py lo refresca en marcha.
        Un dato que falta ahora NO borra el que ya se tenia (un fallo puntual de `tailscale status`
        no deja al movil fuera)."""
        datos = datos or {}
        host = datos.get("host") or self.tailnet_host
        dueno = os.environ.get("NEXO_TAILNET_DUENO") or datos.get("dueno") or self.tailnet_dueno
        cambio = (host, dueno) != (self.tailnet_host, self.tailnet_dueno)
        self.tailnet_host, self.tailnet_dueno = host, dueno
        return cambio

    @property
    def hosts_locales(self) -> set[str]:
        return {f"127.0.0.1:{self.puerto}", f"localhost:{self.puerto}"}

    @property
    def hosts_tailnet(self) -> set[str]:
        # Serve por 443 manda el Host sin puerto; se acepta tambien con :443 por si acaso.
        return {self.tailnet_host, f"{self.tailnet_host}:443"} if self.tailnet_host else set()

    @property
    def hosts(self) -> set[str]:
        return self.hosts_locales | self.hosts_tailnet

    @property
    def origenes(self) -> set[str]:
        return ({f"http://{h}" for h in self.hosts_locales}
                | ({f"https://{self.tailnet_host}"} if self.tailnet_host else set()))
