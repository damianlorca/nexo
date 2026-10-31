"""Reintenta crear la maquina GRATUITA de Oracle para NEXO nube (T1031) hasta que haya hueco, y avisa (24/10).

Uso:
  .venv-oracle\\Scripts\\python.exe herramientas_nube\\oracle_reintentar.py --probar   # solo comprueba, no crea nada
  .venv-oracle\\Scripts\\python.exe herramientas_nube\\oracle_reintentar.py            # UN intento (lo llama la tarea
                                                                                        # programada cada 10 min)

Que hace cada intento:
- Lee la clave de la API de Oracle de C:\\Users\\damia\\.oci\\config (la crea Damian; este script NUNCA la muestra).
- Si ya existe una maquina "nexo-nube" viva, no crea otra: avisa con su IP y desactiva la tarea programada.
- Si no, pide UNA maquina SIEMPRE GRATUITA: VM.Standard.A1.Flex, 1 OCPU, 6 GB, Ubuntu 24.04, disco de 50 GB
  (Always Free: hasta 4 OCPU/24 GB de A1 por cuenta en horas y 200 GB de disco en total). Nada mas.
- "Out of host capacity" o demasiadas peticiones: lo anota y espera al siguiente intento.
- A los 14 dias sin hueco se rinde: avisa y desactiva la tarea. Nunca queda activo todo el ano.
- Cualquier otro error: avisa y se para (mejor parar que insistir a ciegas).
Estado en memoria/oracle_nube.json. Avisos por el sistema de avisos de NEXO (web y movil).
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESTADO = RAIZ / "memoria" / "oracle_nube.json"
TAREA = "NEXO oracle reintentar"
NOMBRE = "nexo-nube"
FORMA = "VM.Standard.A1.Flex"
OCPUS, MEMORIA_GB, DISCO_GB = 1, 6, 50
DIAS_MAXIMO = 14
CLAVE_SSH = Path.home() / ".ssh" / "nexo-nube"
CLOUD_INIT = """#cloud-config
package_update: true
packages: [git, python3-venv, python3-pip, ffmpeg]
runcmd:
  - curl -fsSL https://tailscale.com/install.sh | sh
"""


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar(e: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def _avisar(titulo: str, cuerpo: str) -> None:
    try:
        sys.path.insert(0, str(RAIZ))
        from nucleo import avisos
        avisos.emitir("nube", titulo, cuerpo, ruta="/", clave=f"nube:{titulo}")
    except Exception as ex:  # noqa: BLE001 - el aviso no debe tumbar el intento
        print("no se pudo avisar:", type(ex).__name__)


def _apagar_tarea() -> None:
    subprocess.run(["schtasks", "/Change", "/TN", TAREA, "/DISABLE"], capture_output=True, timeout=30,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _clave_ssh_publica() -> str:
    """Par de claves SSH propio de esta maquina en ~/.ssh/nexo-nube (se crea una vez; la privada no sale del PC)."""
    pub = CLAVE_SSH.with_suffix(".pub")
    if not pub.is_file():
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
        k = ed25519.Ed25519PrivateKey.generate()
        CLAVE_SSH.parent.mkdir(parents=True, exist_ok=True)
        CLAVE_SSH.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                              serialization.NoEncryption()))
        pub.write_bytes(k.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                                    serialization.PublicFormat.OpenSSH) + b" nexo-nube\n")
    return pub.read_text(encoding="ascii").strip()


def _clientes():
    import oci
    cfg = oci.config.from_file()
    oci.config.validate_config(cfg)
    return oci, cfg, oci.core.ComputeClient(cfg), oci.core.VirtualNetworkClient(cfg), oci.identity.IdentityClient(cfg)


def _maquina_viva(oci, comp, compute):
    for i in oci.pagination.list_call_get_all_results(compute.list_instances, comp).data:
        if i.display_name == NOMBRE and i.lifecycle_state not in ("TERMINATED", "TERMINATING"):
            return i
    return None


def _ip_publica(oci, comp, compute, red, inst) -> str:
    for va in compute.list_vnic_attachments(comp, instance_id=inst.id).data:
        v = red.get_vnic(va.vnic_id).data
        if v.public_ip:
            return v.public_ip
    return ""


def _subred(oci, comp, red) -> str:
    """Una subred publica: la que ya haya (la consola creo una al intentarlo) o una nueva nexo-vcn. Las redes son gratis."""
    for s in red.list_subnets(comp).data:
        if s.lifecycle_state == "AVAILABLE" and not s.prohibit_public_ip_on_vnic:
            return s.id
    m = oci.core.models
    vcn = red.create_vcn(m.CreateVcnDetails(cidr_blocks=["10.0.0.0/16"], compartment_id=comp,
                                            display_name="nexo-vcn", dns_label="nexovcn")).data
    oci.wait_until(red, red.get_vcn(vcn.id), "lifecycle_state", "AVAILABLE")
    igw = red.create_internet_gateway(m.CreateInternetGatewayDetails(compartment_id=comp, vcn_id=vcn.id,
                                                                     is_enabled=True, display_name="nexo-igw")).data
    oci.wait_until(red, red.get_internet_gateway(igw.id), "lifecycle_state", "AVAILABLE")
    red.update_route_table(vcn.default_route_table_id, m.UpdateRouteTableDetails(route_rules=[
        m.RouteRule(destination="0.0.0.0/0", destination_type="CIDR_BLOCK", network_entity_id=igw.id)]))
    sub = red.create_subnet(m.CreateSubnetDetails(cidr_block="10.0.0.0/24", compartment_id=comp, vcn_id=vcn.id,
                                                  display_name="nexo-subred", dns_label="nexosub")).data
    oci.wait_until(red, red.get_subnet(sub.id), "lifecycle_state", "AVAILABLE")
    return sub.id


def _imagen(comp, compute) -> str:
    imgs = compute.list_images(comp, operating_system="Canonical Ubuntu", operating_system_version="24.04",
                               shape=FORMA, sort_by="TIMECREATED", sort_order="DESC").data
    if not imgs:
        raise RuntimeError("no encuentro la imagen de Ubuntu 24.04 para A1")
    return imgs[0].id


def probar() -> int:
    oci, cfg, compute, red, ident = _clientes()
    comp = cfg["tenancy"]
    ads = [a.name for a in ident.list_availability_domains(comp).data]
    print("credenciales: ok | region:", cfg.get("region"), "| zonas:", ads)
    print("imagen Ubuntu 24.04 A1:", "ok" if _imagen(comp, compute) else "no")
    print("subredes existentes:", len(red.list_subnets(comp).data))
    viva = _maquina_viva(oci, comp, compute)
    print("maquina nexo-nube:", viva.lifecycle_state if viva else "no existe")
    print("clave ssh publica:", "ok" if _clave_ssh_publica() else "no")
    return 0


def intento() -> int:
    e = _estado()
    if e.get("estado") in ("creada", "rendido", "error"):
        print("nada que hacer:", e.get("estado"))
        _apagar_tarea()
        return 0
    e.setdefault("inicio", _ahora())
    e["estado"] = "buscando"
    limite = datetime.fromisoformat(e["inicio"]) + timedelta(days=DIAS_MAXIMO)
    if datetime.now() > limite:
        e.update(estado="rendido", fin=_ahora())
        _guardar(e)
        _avisar("Oracle: sin hueco en 14 días", f"{e.get('intentos', 0)} intentos sin hueco en Madrid. He parado de "
                                                 "intentarlo. Seguimos con el PC.")
        _apagar_tarea()
        return 0
    oci, cfg, compute, red, ident = _clientes()
    comp = cfg["tenancy"]
    viva = _maquina_viva(oci, comp, compute)
    if viva is None:
        e["intentos"] = int(e.get("intentos", 0)) + 1
        e["ultimo"] = _ahora()
        m = oci.core.models
        try:
            ad = ident.list_availability_domains(comp).data[0].name
            detalles = m.LaunchInstanceDetails(
                availability_domain=ad, compartment_id=comp, display_name=NOMBRE, shape=FORMA,
                shape_config=m.LaunchInstanceShapeConfigDetails(ocpus=OCPUS, memory_in_gbs=MEMORIA_GB),
                source_details=m.InstanceSourceViaImageDetails(image_id=_imagen(comp, compute),
                                                               boot_volume_size_in_gbs=DISCO_GB),
                create_vnic_details=m.CreateVnicDetails(subnet_id=_subred(oci, comp, red), assign_public_ip=True),
                metadata={"ssh_authorized_keys": _clave_ssh_publica(),
                          "user_data": base64.b64encode(CLOUD_INIT.encode()).decode()})
            viva = compute.launch_instance(detalles).data
        except oci.exceptions.ServiceError as ex:
            texto = f"{ex.status} {ex.code} {ex.message}"
            if ex.status == 429 or "capacity" in texto.lower():
                e["ultimo_resultado"] = "sin hueco" if "capacity" in texto.lower() else "demasiadas peticiones"
                _guardar(e)
                print("sin hueco todavia:", e["ultimo_resultado"], "| intentos:", e["intentos"])
                return 0
            e.update(estado="error", ultimo_resultado=texto[:300])
            _guardar(e)
            _avisar("Oracle: error al crear la máquina", texto[:300])
            _apagar_tarea()
            return 1
    for _ in range(40):                       # hasta ~10 min a que arranque
        viva = compute.get_instance(viva.id).data
        if viva.lifecycle_state == "RUNNING":
            break
        time.sleep(15)
    ip = _ip_publica(oci, comp, compute, red, viva)
    e.update(estado="creada", fin=_ahora(), instancia=viva.id, ip=ip, ultimo_resultado=viva.lifecycle_state)
    _guardar(e)
    _avisar("Oracle: máquina creada", f"nexo-nube está {viva.lifecycle_state} con IP {ip or '(pendiente)'}. "
                                      f"Díselo al coordinador para seguir con T1031.")
    _apagar_tarea()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ))
    from nucleo import ayuda
    ayuda.atender(__doc__)
    raise SystemExit(probar() if "--probar" in sys.argv[1:] else intento())
