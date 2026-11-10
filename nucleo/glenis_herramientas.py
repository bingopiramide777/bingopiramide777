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
                                    "(por PayPal o USDT, hecho a mano).",
              {"correo": {"type": "string", "description": "Correo del jugador"},
               "importe": {"type": "string", "description": "Cantidad pagada"},
               "referencia": {"type": "string", "description": "Referencia del pago (ID de PayPal o hash de USDT)"}},
              ["correo", "importe"]),
            f("estado_de_cuenta", "Estado de cuenta de un jugador: saldo, total apostado, total "
                                  "ganado, neto, cuántos cartones y premios lleva, y sus últimos "
                                  "movimientos. Úsalo cuando pregunten por la cuenta de alguien.",
              {"correo": {"type": "string", "description": "Correo del jugador"}}, ["correo"]),
            f("listar_ganadores", "Ganadores de las últimas partidas, con lo que se les debe pagar. "
                                  "Sirve para saber a quién hay que acreditarle un premio.",
              {"limite": {"type": "integer", "description": "Cuántas partidas mirar (por defecto 10)"}}),
            f("datos_de_acreditacion", "Datos que hacen falta para acreditarle un premio a un "
                                       "ganador: correo, nombre, monto del premio, partida y "
                                       "referencia, más el instrumento financiero que el ganador "
                                       "tiene registrado (a dónde se le paga) o el aviso de que "
                                       "aún no lo ha registrado. Úsalo para preparar el pago.",
              {"partida": {"type": "string", "description": "Id de la partida (opcional)"},
               "correo": {"type": "string", "description": "Correo del ganador (opcional)"}}),
            f("reporte_de_pagos", "Resumen de lo que hay que pagar y lo ya pagado: premios "
                                  "pendientes de acreditar, pagos manuales anotados, retiros "
                                  "pendientes y depósitos por acreditar.",
              {}),
            f("ver_datos_cobro", "Datos de cobro de un jugador: por dónde y a qué cuenta "
                                 "quiere que le paguen (PayPal o USDT). Úsalo para saber a dónde "
                                 "mandarle un premio o "
                                 "un retiro. No es un pago: solo dice dónde pagarle.",
              {"correo": {"type": "string", "description": "Correo del jugador"}}, ["correo"]),
            f("preparar_pago_ganador", "Prepara el pago de un premio: busca al ganador, mira su "
                                       "ficha de cobro y deja la orden lista (a quién, cuánto, "
                                       "por dónde y una referencia). NO mueve dinero: el pago lo "
                                       "confirma una persona.",
              {"correo": {"type": "string", "description": "Correo del ganador"},
               "importe": {"type": "string", "description": "Cantidad a pagar, por ejemplo '160,00'"},
               "partida": {"type": "string", "description": "Id de la partida (opcional)"}},
              ["correo", "importe"]),
            f("marcar_premio_pagado", "Deja constancia de que un premio ya se le acreditó al "
                                      "ganador (por PayPal o USDT). No mueve el saldo "
                                      "del juego: solo anota el pago.",
              {"correo": {"type": "string", "description": "Correo del ganador"},
               "importe": {"type": "string", "description": "Cantidad pagada"},
               "referencia": {"type": "string", "description": "Referencia o comprobante del pago"}},
              ["correo", "importe"]),
            f("cuentas_admin", "La cuenta de la administración, que es donde "
                               "cae el dinero de los depósitos de los jugadores (Venezuela, "
                               "Colombia, Chile y Estados Unidos): banco, titular y datos de la "
                               "cuenta. Úsalo cuando pregunten a qué cuenta llega el dinero de un "
                               "país. No son cuentas de jugadores: son las de la casa.",
              {"pais": {"type": "string", "enum": ["VE", "CO", "CL", "US"],
                        "description": "Filtra por país. Si se omite, las de todos."}}),
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
                      "el anfitrión se lleva un 10% y la app el 10%."),
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
            "reparto": "El ganador cobra el 80% del bote; el anfitrión se lleva el 10% si la "
                       "sala es de un jugador, y la app el 10%.",
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

    # -- estado de cuenta, ganadores y pagos --

    def _h_estado_de_cuenta(self, correo: str) -> dict:
        correo = (correo or "").strip().lower()
        with self.juego.candado:
            u = self.juego.usuarios.usuario(correo)
            if u is None:
                return {"error": f"No hay ninguna cuenta con {correo}."}
            r = self.juego.almacen.resumen_jugador(correo)
            saldo = self.juego.monedero.saldo(correo)
            movs = self.juego.monedero.historial(correo, 8)
        return {
            "correo": u.correo, "nombre": u.nombre or "(sin nombre)", "rol": u.rol,
            "activo": u.activo, "verificado": u.verificado,
            "saldo": a_texto(saldo),
            "cartones": r["cartones"], "partidas": r["partidas"],
            "premios_ganados": r["premios_ganados"],
            "total_apostado": a_texto(r["total_apostado"]),
            "total_ganado": a_texto(r["total_ganado"]),
            "neto": a_texto(r["total_ganado"] - r["total_apostado"]),
            "ultimos_movimientos": [
                {"tipo": m.tipo, "importe": a_texto(m.centimos), "motivo": m.motivo}
                for m in movs],
        }

    def _h_listar_ganadores(self, limite: int = 10) -> dict:
        limite = int(limite) if isinstance(limite, int) and limite > 0 else 10
        with self.juego.candado:
            filas = self.juego.almacen.partidas(limite)
            salida = []
            for f in filas:
                if not f["ganador"]:
                    continue
                u = self.juego.usuarios.usuario(f["ganador"])
                salida.append({
                    "partida": f["id"], "sala": f["sala"] or "(por defecto)",
                    "ganador": f["ganador"],
                    "nombre": (u.nombre if u and u.nombre else "(sin nombre)"),
                    "premio": a_texto(f["premio"]),
                    "estado_partida": f["estado"],
                })
        return {"ganadores": salida,
                "nota": "El premio se paga al ganador. Usa marcar_premio_pagado cuando lo "
                        "hayas acreditado."}

    def _h_datos_de_acreditacion(self, partida: str = "", correo: str = "") -> dict:
        partida = (partida or "").strip()
        correo = (correo or "").strip().lower()
        with self.juego.candado:
            if partida:
                fila = self.juego.almacen.partida(partida)
                filas = [fila] if fila else []
            else:
                filas = self.juego.almacen.partidas(50)
            datos = []
            for f in filas:
                if f is None or not f["ganador"]:
                    continue
                if correo and f["ganador"] != correo:
                    continue
                u = self.juego.usuarios.usuario(f["ganador"])
                ficha = self.juego.fichas.de_seguro(f["ganador"])
                fila_pago = {
                    "partida": f["id"],
                    "a_acreditar": f["ganador"],
                    "nombre": (u.nombre if u and u.nombre else "(sin nombre)"),
                    "monto": a_texto(f["premio"]),
                    "referencia_sugerida": f"PREMIO-{f['id']}",
                    "sala": f["sala"] or "(por defecto)",
                    # El premio se paga por el instrumento que el ganador tenga
                    # registrado. Sin ficha, no hay a dónde mandarle el dinero.
                    "instrumento_registrado": bool(ficha.configurada),
                }
                if ficha.configurada:
                    fila_pago["metodo_de_pago"] = ficha.metodo
                    fila_pago["datos_de_pago"] = {c["label"]: c["value"]
                                                  for c in ficha.a_dict()["campos"]}
                else:
                    fila_pago["falta"] = ("El ganador no ha registrado dónde recibir el "
                                          "dinero. Hay que pedirle que lo ponga en su perfil "
                                          "antes de poder pagarle.")
                datos.append(fila_pago)
        if not datos:
            return {"aviso": "No hay premios pendientes con esos datos.",
                    "nota": "Para acreditar hacen falta: correo del ganador, monto y referencia."}
        return {"acreditaciones": datos,
                "nota": ("El premio se le acredita al ganador por el instrumento financiero "
                         "que tenga registrado en su perfil. Si no lo ha puesto, no se le "
                         "puede pagar: pídeselo primero. Anota el pago con marcar_premio_pagado.")}

    def _h_reporte_de_pagos(self) -> dict:
        with self.juego.candado:
            filas = self.juego.almacen.partidas(50)
            pendientes = [
                {"partida": f["id"], "ganador": f["ganador"], "premio": a_texto(f["premio"])}
                for f in filas if f["ganador"] and f["premio"] > 0]
            retiros = self.juego.retiros.listar(estado="pendiente")
            depositos = self.juego.depositos.listar(estado="pendiente")
            historial = self.juego.almacen.historial_glenis(200)
        pagos_manuales = [f for f in historial
                          if (f["texto"] or "").startswith(("PAGO MANUAL", "GANADOR"))]
        return {
            "premios_por_acreditar": pendientes,
            "cuantos_premios": len(pendientes),
            "retiros_pendientes": len(retiros),
            "retiros_por_pagar": a_texto(sum(r.centimos for r in retiros)),
            "depositos_por_acreditar": len(depositos),
            "depositos_por_acreditar_monto": a_texto(sum(d.centimos for d in depositos)),
            "pagos_manuales_anotados": [
                {"texto": f["texto"], "cuando": f["cuando"]} for f in reversed(pagos_manuales[:20])],
        }

    def _h_cuentas_admin(self, pais: str = "") -> dict:
        """La cuenta de la CASA (PayPal y USDT): donde cae el dinero de los depósitos."""
        from . import paises as _paises

        code = (pais or "").strip().upper()
        if code and not _paises.es_pais_valido(code):
            return {"error": f"No hay cuenta de administración para el país {code!r}. "
                             "Los países que hay: VE, CO, CL y US."}
        # La cuenta es la misma en todo el mundo: PayPal y la billetera USDT.
        cuentas = _paises.cuentas_admin()
        lista = []
        for c in cuentas:
            lista.append({
                "pais": c.pais,
                "nombre_pais": (_paises.pais(c.pais).nombre if _paises.pais(c.pais) else c.pais),
                "moneda": c.moneda,
                "banco": c.banco,
                "titular": c.titular,
                "configurada": c.configurada,
                "datos": [l.a_dict() for l in c.lineas],
            })
        return {
            "cuentas": lista,
            "aviso": ("Es la cuenta de la CASA (la administración), no de los jugadores. "
                      "Aquí es donde cae el dinero que depositan los jugadores, con PayPal "
                      "o con USDT (cripto). Es la misma para todos los países."),
            "sin_configurar": [c["pais"] for c in lista if not c["configurada"]],
        }

    def _h_ver_datos_cobro(self, correo: str) -> dict:
        correo = (correo or "").strip().lower()
        with self.juego.candado:
            u = self.juego.usuarios.usuario(correo)
            if u is None:
                return {"error": f"No hay ninguna cuenta con {correo}."}
            ficha = self.juego.fichas.de(correo)
        if not ficha.configurada:
            return {"correo": correo, "tiene_ficha": False,
                    "aviso": (f"{correo} todavía no ha dejado sus datos de cobro. "
                              "Pídeselos o dile que los ponga en su perfil.")}
        return {"correo": correo, "tiene_ficha": True,
                "metodo": ficha.metodo,
                "datos": {c["label"]: c["value"] for c in ficha.a_dict()["campos"]},
                "nota": "Son los datos a los que hay que mandarle el dinero."}

    def _h_preparar_pago_ganador(self, correo: str, importe: str, partida: str = "") -> dict:
        correo = (correo or "").strip().lower()
        centimos = a_centimos(importe)
        with self.juego.candado:
            u = self.juego.usuarios.usuario(correo)
            if u is None:
                return {"error": f"No hay ninguna cuenta con {correo}."}
            ficha = self.juego.fichas.de(correo)
            saldo = self.juego.monedero.saldo(correo)
        orden = {
            "a": correo, "nombre": (u.nombre or "(sin nombre)"),
            "importe": a_texto(centimos), "partida": partida or "",
            "referencia": f"PREMIO-{partida}" if partida else "PREMIO",
            "saldo_actual": a_texto(saldo),
        }
        if not ficha.configurada:
            orden["falta"] = "datos de cobro"
            orden["aviso"] = (f"{correo} no tiene datos de cobro puestos. Pídeselos antes de "
                              "pagar, o que los ponga en su perfil.")
            return orden
        orden["metodo"] = ficha.metodo
        orden["datos_de_cobro"] = {c["label"]: c["value"] for c in ficha.a_dict()["campos"]}
        orden["listo_para_pagar"] = True
        orden["aviso"] = ("Orden lista. El pago lo confirma una persona: Glenis no mueve dinero. "
                          "Cuando esté hecho, anótalo con marcar_premio_pagado.")
        return orden

    def _h_marcar_premio_pagado(self, correo: str, importe: str, referencia: str = "") -> dict:
        correo = (correo or "").strip().lower()
        centimos = a_centimos(importe)
        with self.juego.candado:
            if self.juego.usuarios.usuario(correo) is None:
                return {"error": f"No hay ninguna cuenta con {correo}."}
            texto = (f"PREMIO PAGADO: {a_texto(centimos)} acreditados a {correo}"
                     + (f" (referencia {referencia})" if referencia else ""))
            self.juego.almacen.anotar_glenis(
                f"g-{int(time.time() * 1000)}", "Glenis IA", texto, "", time.time())
        return {"ok": True, "anotado": texto,
                "nota": "Queda constancia del pago. No mueve el saldo del juego."}
