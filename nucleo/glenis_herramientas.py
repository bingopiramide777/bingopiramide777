"""Las herramientas de Glenis IA: lo que puede consultar y lo que puede hacer.

Se separan en dos grupos a propósito:

- **Consultar** (ver resumen, buscar jugador, mirar retiros y depósitos): no
  cambian nada. Glenis las usa sin permiso.
- **Actuar** (acreditar un depósito, ajustar un saldo): mueven dinero. Quedan
  todas anotadas con quién lo pidió y cuándo.

Aquí está el porqué de cada freno. Un asistente con acceso al dinero sin frenos
es una máquina de hacer agujeros.
"""

from __future__ import annotations

import time

from .money import a_centimos, a_texto


class Herramientas:
    """Junta las herramientas con el juego (usuarios, monedero, depósitos, retiros)."""

    def __init__(self, juego) -> None:
        self.juego = juego
        self.registro: list[dict] = []

    # -- esquemas que ve la IA --

    def esquemas(self) -> list[dict]:
        def f(nombre, descripcion, propiedades=None, requeridos=None):
            props = dict(propiedades or {})
            requeridos = list(requeridos or [])
            # Un parámetro opcional puede llegar como null (el modelo lo manda así
            # cuando no lo usa). Si el esquema solo admite "string", la validación
            # de la IA rechaza la llamada entera y la herramienta no se ejecuta.
            # Se le permite null a todo lo que no sea obligatorio.
            for clave, definicion in props.items():
                if clave in requeridos:
                    continue
                tipo = definicion.get("type")
                if isinstance(tipo, str) and "null" not in tipo:
                    definicion = dict(definicion, type=[tipo, "null"])
                    props[clave] = definicion
            return {"type": "function", "function": {
                "name": nombre, "description": descripcion,
                "parameters": {"type": "object", "properties": props,
                               "required": requeridos}}}

        return [
            f("resumen", "Resumen del negocio: jugadores, dinero en cuentas, retiros y "
                         "depósitos pendientes, partidas, apostado, pagado y margen."),
            f("buscar_jugador", "Datos de un jugador: saldo, estado, si tiene pregunta secreta, "
                                "y sus últimos movimientos.",
              {"correo": {"type": "string", "description": "Correo del jugador"}}, ["correo"]),
            f("listar_jugadores", "Lista los jugadores con su saldo."),
            f("listar_depositos", "Depósitos declarados por los jugadores, con monto, referencia, "
                                  "banco, fecha y estado.",
              {"estado": {"type": "string", "enum": ["pendiente", "acreditado", "rechazado"],
                          "description": "Filtra por estado. Si se omite, los pendientes."}}),
            f("listar_retiros", "Retiros pedidos por los jugadores.",
              {"estado": {"type": "string", "enum": ["pendiente", "pagado", "rechazado"],
                          "description": "Filtra por estado. Si se omite, los pendientes."}}),
            f("listar_partidas", "Últimas partidas: cartones, bolas, ganador y premio."),
            f("listar_salas", "Las salas de bingo: nombre, modo, precio del cartón y de quién "
                              "son. Las salas de jugadores pagan un 10% al anfitrión."),
            f("ganancias", "Cuánto dinero ha dejado el bingo: botes, premios pagados, comisiones "
                           "de anfitriones y lo que queda a la app.",
              {"correo": {"type": "string", "description": "Opcional: el correo de un anfitrión, "
                           "para ver solo sus ganancias"}}),
            f("acreditar_deposito", "Da por bueno un depósito y SUMA el dinero al saldo del jugador. "
                                    "Úsalo solo cuando el administrador lo confirme.",
              {"id": {"type": "string", "description": "El id del depósito, que empieza por 'd-'"},
               "nota": {"type": "string", "description": "Motivo o comprobación hecha"}}, ["id"]),
            f("rechazar_deposito", "Rechaza un depósito. No mueve dinero.",
              {"id": {"type": "string", "description": "El id del depósito"},
               "nota": {"type": "string", "description": "Motivo del rechazo"}}, ["id"]),
            f("ajustar_saldo", "Suma o resta dinero del saldo de un jugador a mano (bono, corrección). "
                               "Queda anotado a tu nombre.",
              {"correo": {"type": "string", "description": "Correo del jugador"},
               "importe": {"type": "string", "description": "Cantidad, por ejemplo '50,00'"},
               "signo": {"type": "string", "enum": ["sumar", "restar"], "description": "Qué hacer"},
               "motivo": {"type": "string", "description": "Por qué se hace"}},
              ["correo", "importe", "motivo"]),
            f("declarar_ganador", "Deja constancia de que un jugador ha ganado una partida, para "
                                  "avisar a la administración de que hay que pagarle.",
              {"correo": {"type": "string", "description": "Correo del ganador"},
               "premio": {"type": "string", "description": "Cantidad a pagar, por ejemplo '160,00'"},
               "partida": {"type": "string", "description": "Id de la partida, si se sabe"}},
              ["correo", "premio"]),
            f("anotar_pago_manual", "Anota que la administración ya pagó un premio por fuera "
                                    "(transferencia o Pago Móvil hecho a mano).",
              {"correo": {"type": "string", "description": "Correo del jugador"},
               "importe": {"type": "string", "description": "Cantidad pagada"},
               "referencia": {"type": "string", "description": "Referencia de la transferencia"}},
              ["correo", "importe"]),
        ]

    # -- ejecución --

    def ejecutar(self, nombre: str, argumentos: dict) -> dict:
        try:
            metodo = getattr(self, f"_h_{nombre}", None)
            if metodo is None:
                return {"error": f"No existe la herramienta {nombre!r}."}
            resultado = metodo(**argumentos)
            self.registro.append({"herramienta": nombre, "argumentos": argumentos,
                                  "cuando": time.time()})
            return resultado
        except TypeError as exc:
            return {"error": f"Argumentos mal: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # -- consultar --

    def _h_resumen(self) -> dict:
        with self.juego.candado:
            r = self.juego.resumen()
        return {
            "jugadores": r["jugadores"],
            "administradores": r["usuarios"] - r["jugadores"],
            "dinero_en_cuentas": a_texto(r["total_en_cuentas"]),
            "retiros_pendientes": r["retiros_pendientes"],
            "retiros_por_pagar": a_texto(r["total_pendiente"]),
            "depositos_pendientes": r["depositos_pendientes"],
            "depositos_por_acreditar": a_texto(r["depositos_pendiente_centimos"]),
            "partidas": r["partidas"], "apostado": a_texto(r["apostado"]),
            "pagado_en_premios": a_texto(r["pagado"]), "margen": a_texto(r["margen"]),
        }

    def _h_listar_salas(self) -> dict:
        with self.juego.candado:
            salas = self.juego.salas.todas()
            cuentas = []
            for s in salas:
                d = s.a_dict()
                d["precio"] = a_texto(s.precio_carton)
                cuentas.append(d)
        return {
            "salas": cuentas,
            "de_la_casa": sum(1 for s in salas if not s.es_de_jugador),
            "de_jugadores": sum(1 for s in salas if s.es_de_jugador),
            "aviso": ("El ganador siempre cobra el 80% del bote. En las salas de un jugador, "
                      "el anfitrión se lleva un 10% y la app el otro 10%."),
        }

    def _h_ganancias(self, correo: str = "") -> dict:
        with self.juego.candado:
            if (correo or "").strip():
                g = self.juego.salas.ganancias(correo.strip().lower())
                return {"anfitrion": g["correo"], "salas": g["salas"], "partidas": g["partidas"],
                        "botes": g["botes_texto"], "comision_anfitrion": g["anfitrion_texto"],
                        "queda_a_la_app": g["app_texto"]}
            e = self.juego.salas.economia()
        return {
            "partidas_terminadas": e["partidas"],
            "botes_totales": e["botes_texto"],
            "premios_pagados": e["premios_texto"],
            "comisiones_a_anfitriones": e["comisiones_texto"],
            "ganancia_de_la_app": e["app_texto"],
            "reparto": "El ganador cobra el 80% del bote; la app se queda el 20% (10% de ese "
                       "20% es para el anfitrión si la sala es de un jugador).",
        }

    def _h_buscar_jugador(self, correo: str) -> dict:
        correo = (correo or "").strip().lower()
        with self.juego.candado:
            u = self.juego.usuarios.usuario(correo)
            if u is None:
                return {"error": f"No hay ninguna cuenta con {correo}."}
            saldo = self.juego.monedero.saldo(correo)
            movs = self.juego.monedero.historial(correo, 8)
        return {
            "correo": u.correo, "nombre": u.nombre or "(sin nombre)", "rol": u.rol,
            "activo": u.activo, "tiene_pregunta_secreta": bool(self.juego.usuarios.pregunta_de(correo)),
            "saldo": a_texto(saldo),
            "ultimos_movimientos": [
                {"tipo": m.tipo, "importe": a_texto(m.centimos), "motivo": m.motivo}
                for m in movs
            ],
        }

    def _h_listar_jugadores(self) -> dict:
        """Lista las cuentas. Se marca el rol: un admin NO es un jugador."""
        with self.juego.candado:
            gente = self.juego.usuarios.usuarios()
            cuentas = [{"correo": u.correo, "nombre": u.nombre or "(sin nombre)", "rol": u.rol,
                        "activo": u.activo, "saldo": a_texto(self.juego.monedero.saldo(u.correo))}
                       for u in gente]
        return {"cuentas": cuentas,
                "jugadores": sum(1 for c in cuentas if c["rol"] == "jugador"),
                "aviso": "Cuenta solo como jugadores las que tienen rol 'jugador'."}

    def _h_listar_depositos(self, estado: str = "pendiente") -> dict:
        with self.juego.candado:
            lista = self.juego.depositos.listar(estado=estado or "pendiente")
        return {"depositos": [
            {"id": d.id, "jugador": d.correo, "monto": a_texto(d.centimos), "metodo": d.metodo,
             "referencia": d.referencia, "banco": d.banco, "dia": d.dia, "estado": d.estado}
            for d in lista]}

    def _h_listar_retiros(self, estado: str = "pendiente") -> dict:
        with self.juego.candado:
            lista = self.juego.retiros.listar(estado=estado or "pendiente")
        return {"retiros": [
            {"id": r.id, "jugador": r.correo, "importe": a_texto(r.centimos), "metodo": r.metodo,
             "datos": r.detalles, "estado": r.estado}
            for r in lista]}

    def _h_listar_partidas(self) -> dict:
        with self.juego.candado:
            filas = self.juego.almacen.partidas(10)
            return {"partidas": [
                {"id": f["id"], "estado": f["estado"], "cartones": len(self.juego.almacen.cartones(f["id"])),
                 "bolas": len([n for n in f["bolas"].split(",") if n]),
                 "ganador": f["ganador"] or "(sin ganador)", "premio": a_texto(f["premio"])}
                for f in filas]}

    # -- actuar --

    def _h_acreditar_deposito(self, id: str, nota: str = "") -> dict:
        with self.juego.candado:
            d = self.juego.depositos.acreditar(id, "Glenis IA", nota or "acreditado por Glenis IA")
            saldo = self.juego.monedero.saldo(d.correo)
        return {"ok": True, "deposito": d.id, "jugador": d.correo, "acreditado": a_texto(d.centimos),
                "saldo_nuevo": a_texto(saldo),
                "aviso": "Queda anotado a nombre de Glenis IA en el registro."}

    def _h_rechazar_deposito(self, id: str, nota: str = "") -> dict:
        with self.juego.candado:
            d = self.juego.depositos.rechazar(id, "Glenis IA", nota or "rechazado por Glenis IA")
        return {"ok": True, "deposito": d.id, "estado": d.estado}

    def _h_ajustar_saldo(self, correo: str, importe: str, motivo: str,
                         signo: str = "sumar") -> dict:
        correo = (correo or "").strip().lower()
        if not motivo or len(motivo.strip()) < 3:
            return {"error": "Hace falta un motivo para tocar el saldo."}
        centimos = a_centimos(importe)
        if signo == "restar":
            centimos = -centimos
        with self.juego.candado:
            self.juego.monedero.ajustar(correo, centimos, f"{motivo} (Glenis IA)")
            saldo = self.juego.monedero.saldo(correo)
        return {"ok": True, "jugador": correo, "saldo_nuevo": a_texto(saldo)}

    def _h_declarar_ganador(self, correo: str, premio: str, partida: str = "") -> dict:
        correo = (correo or "").strip().lower()
        with self.juego.candado:
            if self.juego.usuarios.usuario(correo) is None:
                return {"error": f"No hay ninguna cuenta con {correo}."}
            centimos = a_centimos(premio)
            aviso = (f"GANADOR: {correo} ganó {a_texto(centimos)}"
                     + (f" en la partida {partida}" if partida else ""))
            self.juego.almacen.anotar_glenis(
                f"g-{int(time.time() * 1000)}", "Glenis IA", aviso,
                "", time.time())
        return {"ok": True, "aviso_registrado": aviso,
                "nota": "El pago lo tiene que hacer la administración."}

    def _h_anotar_pago_manual(self, correo: str, importe: str, referencia: str = "") -> dict:
        correo = (correo or "").strip().lower()
        centimos = a_centimos(importe)
        with self.juego.candado:
            if self.juego.usuarios.usuario(correo) is None:
                return {"error": f"No hay ninguna cuenta con {correo}."}
            texto = (f"PAGO MANUAL: se pagaron {a_texto(centimos)} a {correo}"
                     + (f" (referencia {referencia})" if referencia else ""))
            self.juego.almacen.anotar_glenis(
                f"g-{int(time.time() * 1000)}", "Glenis IA", texto, "", time.time())
        return {"ok": True, "anotado": texto,
                "nota": "Esto NO mueve el saldo del juego: es solo constancia del pago por fuera."}
