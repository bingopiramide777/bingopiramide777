"""Sistema de referidos: quien trae jugadores cobra por ellos.

Cada cuenta tiene un código de amigo. Cuando alguien se registra con ese código,
queda apadrinado de por vida. A partir de ahí, cada vez que el ahijado gana un
puesto, el padrino cobra una comisión.

La comisión sale SIEMPRE de la parte de la app, nunca del premio del ganador ni
de la comisión del anfitrión: el reparto 80/10/10 no se toca. Así el sistema de
referidos no puede dejar el bote en números rojos, pase lo que pase.

El porcentaje se ajusta por entorno (``BINGO_REFERIDO_PCT``), con tope: la app
nunca reparte entre padrinos más de lo que ella misma se llevó de esa partida.
"""

from __future__ import annotations

import os
import secrets
import time

from .almacen import Almacen

# Qué parte de la ganancia de la app se lleva el padrino, en %.
COMISION_POR_DEFECTO = 10


def porcentaje() -> int:
    """El % de la ganancia de la app que se lleva el padrino, leído del entorno."""
    try:
        valor = int(os.environ.get("BINGO_REFERIDO_PCT", "") or COMISION_POR_DEFECTO)
    except ValueError:
        return COMISION_POR_DEFECTO
    return valor if 0 <= valor <= 100 else COMISION_POR_DEFECTO


class ErrorDeReferidos(ValueError):
    """No se pudo resolver la comisión de un referido."""


class Referidos:
    def __init__(self, almacen: Almacen) -> None:
        self.almacen = almacen

    # -- consultas --

    def porcentaje(self) -> int:
        """El % de la ganancia de la app que se lleva el padrino."""
        return porcentaje()

    def padrino_de(self, correo: str) -> str:
        fila = self.almacen.usuario((correo or "").strip().lower())
        if fila is None:
            return ""
        claves = fila.keys()
        return (fila["referido_por"] if "referido_por" in claves else "") or ""

    def codigo_de(self, correo: str) -> str:
        fila = self.almacen.usuario((correo or "").strip().lower())
        if fila is None:
            return ""
        claves = fila.keys()
        return (fila["codigo_amigo"] if "codigo_amigo" in claves else "") or ""

    def resumen(self, correo: str) -> dict:
        """Lo que ve un jugador en su pantalla de referidos."""
        from .money import a_texto

        correo = (correo or "").strip().lower()
        invitados = self.almacen.invitados_de(correo)
        movimientos = self.almacen.referidos_de(correo)
        total = self.almacen.total_referidos(correo)
        return {
            "codigo": self.codigo_de(correo),
            "pct": porcentaje(),
            "invitados": len(invitados),
            "comisiones": len(movimientos),
            "total": total,
            "total_texto": a_texto(total),
            "detalle": [
                {"invitado": m["referido"], "centimos": m["centimos"],
                 "texto": a_texto(m["centimos"]), "cuando": m["cuando"]}
                for m in movimientos
            ],
        }

    # -- liquidación --

    def liquidar(self, partida_id: str, ganadores: list[dict], reparto: dict,
                 monedero) -> list[dict]:
        """Paga a los padrinos de los ganadores de una partida. No repite pago.

        `ganadores` son los puestos ya resueltos (cada uno con su correo). La
        comisión de cada padrino sale de la parte de la app de esa partida y,
        entre todos, nunca se reparte más de esa parte.
        """
        app = int(reparto.get("app", 0) or 0)
        pct = porcentaje()
        if app <= 0 or pct <= 0:
            return []

        # Un padrino puede apadrinar a varios ganadores de la misma partida; se
        # agrupa por padrino para pagarle una sola vez por partida.
        por_padrino: dict[str, list[str]] = {}
        for g in ganadores:
            correo = (g.get("correo") or "").strip().lower()
            if not correo:
                continue
            padrino = self.padrino_de(correo)
            if padrino and padrino != correo:
                por_padrino.setdefault(padrino, []).append(correo)
        if not por_padrino:
            return []

        bruto = app * pct // 100
        # Lo que ya se pagó en esta partida (p. ej. en un puesto anterior) se
        # descuenta: entre todos los padrinos nunca se reparte más de la app.
        disponible = app - self.almacen.pagado_en_partida(partida_id)
        if disponible <= 0:
            return []
        if bruto * len(por_padrino) > disponible:
            bruto = disponible // len(por_padrino)
        if bruto <= 0:
            return []

        pagos = []
        for padrino, ahijados in por_padrino.items():
            mov_id = f"r-{secrets.token_hex(6)}"
            anotado = self.almacen.anotar_referido(
                mov_id, partida_id, ",".join(ahijados), padrino, bruto, time.time())
            if not anotado:
                # Ya se pagó esta comisión (reintento): no se paga dos veces.
                continue
            monedero.pagar_premio(
                padrino, bruto, motivo=f"comisión de referido (partida {partida_id})")
            pagos.append({"padrino": padrino, "centimos": bruto, "ahijados": ahijados})
        return pagos
