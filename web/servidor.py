"""Servidor web de Bingo Pirámide 777.

Solo biblioteca estándar: http.server y sqlite3. Sin dependencias que instalar.
Sirve la interfaz del jugador, el panel de administración y la API.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from bingo import MesaBingo, Sala
from nucleo import Almacen, ErrorDeDinero, ErrorDeMonedero, Monedero, Usuarios, a_centimos, a_texto
from nucleo.almacen_pg import abrir_almacen
from nucleo.correo import Correo, ErrorDeCorreo
from nucleo.datos_cobro import CAMPOS as _CAMPOS_COBRO
from nucleo.datos_cobro import METODOS as _METODOS_COBRO
from nucleo.billeteras import Billeteras
from nucleo.cobros import Cobros
from nucleo.depositos import METODOS as METODOS_DEPOSITO
from nucleo.depositos import ErrorDeDeposito, Depositos
from nucleo.fichas import ErrorDeFicha, FichasCobro
from nucleo.firmas import REDES as REDES_BILLETERA
from nucleo.glenis import ErrorDeGlenis, Glenis
from nucleo.glenis_herramientas import Herramientas
from nucleo.idiomas import IDIOMAS
from nucleo.referidos import Referidos
from nucleo.retiros import ErrorDeRetiro, Retiros
from nucleo.salas import (SALA_CASA_ID, SALA_CASA_NOMBRE, ErrorDeSalas, Salas)

RAIZ_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
CORREO_ADMIN_POR_DEFECTO = "bingopiramide777@gmail.com"
NOMBRES_PUESTO = ("Primer lugar", "Segundo lugar", "Tercer lugar")


class Juego:
    """Estado de la aplicación: base de datos, usuarios, monedero, bingo y retiros.

    Un candado protege el dinero. Es un servidor pequeño, y así el saldo nunca se
    descuadra por dos peticiones que entren a la vez.
    """

    def __init__(self, almacen: Almacen | None = None, correo_admin: str | None = None,
                 clave_admin: str | None = None) -> None:
        self.candado = threading.RLock()
        # Con DATABASE_URL se usa Postgres (los datos sobreviven a los reinicios);
        # sin ella, el fichero SQLite de siempre.
        self.almacen = almacen or abrir_almacen()
        self.usuarios = Usuarios(self.almacen)
        self.monedero = Monedero(self.almacen)
        self.retiros = Retiros(self.almacen, self.monedero)
        self.depositos = Depositos(self.almacen, self.monedero)
        self.referidos = Referidos(self.almacen)
        self.fichas = FichasCobro(self.almacen)
        self.billeteras = Billeteras(self.almacen)
        self.correo_admin = (correo_admin or os.environ.get("BINGO_ADMIN_EMAIL")
                             or CORREO_ADMIN_POR_DEFECTO)
        # La cuenta de administración es el anfitrión de la sala de trabajo.
        self.salas = Salas(self.almacen, usuarios=self.usuarios,
                           anfitrion_casa=self.correo_admin)
        # El sistema de cobro: define, suma y audita todos los cobros del proyecto.
        self.cobros = Cobros(self.almacen, salas=self.salas, depositos=self.depositos)
        self.herramientas = Herramientas(self)
        self.glenis = Glenis(self.herramientas.esquemas(), self.herramientas.ejecutar)
        self.correo = Correo()
        # El repartidor decide cómo se parte cada bote según la sala de la partida.
        self.mesa = MesaBingo(sala=Sala(), monedero=self.monedero,
                              repartidor=self._reparto_de_partida)
        self._partida = None
        self._partida_id = ""
        self._partida_sala = "sala-zulia"
        self.clave_admin = clave_admin or os.environ.get("BINGO_ADMIN_CLAVE") or ""
        self._crear_admin()

    def _reparto_de_partida(self, partida_id: str, bote: int) -> dict:
        """Parte el bote según la sala de la partida. Lo llama el motor de bingo."""
        partida = self.mesa.sala.partidas.get(partida_id)
        sala_id = getattr(partida, "sala", "") if partida else ""
        fila = self.almacen.sala(sala_id) if sala_id else None
        if fila and fila["es_evento"]:
            from nucleo.salas import reparto_evento
            porcentajes = tuple(int(p) for p in (fila["premios_pct"] or "").split(",") if p)
            reparto = reparto_evento(bote, porcentajes)
            reparto["anfitrion"] = 0
            reparto["anfitrion_correo"] = ""
            reparto["con_anfitrion"] = False
            return reparto
        from nucleo.salas import reparto_del_bote
        # El reparto lo decide la sala: 80/20 en las de la casa, 70/10/20 en las de
        # jugador y 80/15/5 en la sala de trabajo.
        if not sala_id or fila is None:
            reparto = reparto_del_bote(bote, con_anfitrion=False)
            reparto["anfitrion_correo"] = ""
            return reparto
        reparto = self.salas.reparto_de_sala(sala_id, bote)
        reparto["anfitrion_correo"] = self.anfitrion_de(partida_id)
        return reparto

    def anfitrion_de(self, partida_id: str) -> str:
        """Correo del anfitrión de la sala de esa partida (vacío si es de la casa)."""
        partida = self.mesa.sala.partidas.get(partida_id)
        sala_id = getattr(partida, "sala", "") if partida else ""
        if not sala_id:
            return ""
        fila = self.almacen.sala(sala_id)
        return fila["dueno"] if fila else ""

    def comprobar_aforo(self, partida, jugador: str) -> None:
        """Comprueba que la sala admite a un jugador más.

        El aforo cuenta jugadores distintos, no cartones: quien ya está dentro
        puede comprar más cartones aunque la sala esté llena. Lo pone la
        administración en cualquier sala; 0 = sin límite.
        """
        sala_id = getattr(partida, "sala", "")
        fila = self.almacen.sala(sala_id) if sala_id else None
        if not fila:
            return
        aforo = int(fila["aforo"] or 0)
        if aforo <= 0 or jugador in partida.jugadores():
            return
        if len(partida.jugadores()) >= aforo:
            from nucleo.salas import ErrorDeSalas
            raise ErrorDeSalas(f"La sala está llena: {aforo} jugadores como máximo.")

    def comprobar_cupo(self, partida) -> None:
        """Comprueba que la sala no ha agotado sus cartones (cupo = 0 es sin tope)."""
        sala_id = getattr(partida, "sala", "")
        fila = self.almacen.sala(sala_id) if sala_id else None
        if not fila:
            return
        cupo = int(fila["cupo_cartones"] or 0)
        if cupo <= 0:
            return
        if len(partida.cartones) >= cupo:
            from nucleo.salas import ErrorDeSalas
            raise ErrorDeSalas(f"Se agotaron los {cupo} cartones de esta sala.")

    def comprobar_max_cartones(self, partida, jugador: str, cuantos: int) -> None:
        """Comprueba que el jugador no pasa del tope de cartones de la sala.

        Es un tope por jugador, no por sala: en la sala de jugar desde casa
        nadie puede acaparar el bote con más de 6 cartones. 0 = sin tope.
        """
        sala_id = getattr(partida, "sala", "")
        fila = self.almacen.sala(sala_id) if sala_id else None
        if not fila or "max_cartones" not in fila.keys():
            return
        tope = int(fila["max_cartones"] or 0)
        if tope <= 0:
            return
        ya = len(partida.cartones_de(jugador))
        if ya + cuantos > tope:
            from nucleo.salas import ErrorDeSalas
            if ya >= tope:
                raise ErrorDeSalas(f"Ya tienes el máximo de {tope} cartones en esta sala.")
            raise ErrorDeSalas(
                f"En esta sala se pueden comprar {tope} cartones como máximo por jugador "
                f"(ya tienes {ya}).")

    def info_evento(self) -> dict:
        """Todo lo que la web necesita del evento: aforo, ocupación y premios."""
        sala = self.salas.evento()
        partida = self.partida(sala.id)
        jugadores = len(partida.jugadores())
        bote = partida.precio_carton * len(partida.cartones)
        porcentajes = list(sala.premios_pct)
        premios = [
            {"puesto": i + 1, "pct": pct,
             "pct_texto": f"{pct} %",
             "premio": bote * pct // 100,
             "premio_texto": a_texto(bote * pct // 100)}
            for i, pct in enumerate(porcentajes)
        ]
        aforo = sala.aforo
        return {
            "id": sala.id,
            "nombre": sala.nombre,
            "modo": sala.modo,
            "precio_carton": sala.precio_carton,
            "precio_texto": a_texto(sala.precio_carton),
            "aforo": aforo,
            "aforo_texto": "Sin límite" if aforo <= 0 else f"{aforo} jugadores",
            "jugadores": jugadores,
            "plazas_libres": None if aforo <= 0 else max(0, aforo - jugadores),
            "llena": bool(aforo > 0 and jugadores >= aforo),
            "activa": sala.activa,
            "bote": bote,
            "bote_texto": a_texto(bote),
            "premios": premios,
            "cartones": len(partida.cartones),
            "ganadores": list(partida.ganadores),
            "plazas": partida.plazas,
            "estado": partida.estado,
            "tipo_juego": sala.tipo_juego,
            "cupo_cartones": sala.cupo_cartones,
            "max_cartones": sala.max_cartones,
            "fecha_partida": sala.fecha_partida,
        }

    def _crear_admin(self) -> None:
        """Crea la cuenta de administración si no existe.

        Si no hay clave configurada, se genera una y se muestra una sola vez por
        consola. Es mejor una clave aleatoria que una por defecto que todos saben.
        """
        if self.usuarios.usuario(self.correo_admin):
            # Ya existe: puede ser de antes de los referidos, así que se asegura
            # que tenga su código de amigo y el de invitación a la sala de trabajo.
            self.usuarios.asegurar_codigo_amigo(self.correo_admin)
            self.usuarios.asegurar_codigo_invitacion(self.correo_admin)
            return
        clave = self.clave_admin
        generada = False
        if not clave:
            clave = secrets.token_urlsafe(12)
            generada = True
        self.usuarios.asegurar_admin(self.correo_admin, clave)
        # La cuenta de administración también participa en los referidos y en la
        # sala de trabajo: se le dan sus dos códigos para que sus pantallas no
        # salgan vacías.
        self.usuarios.asegurar_codigo_amigo(self.correo_admin)
        self.usuarios.asegurar_codigo_invitacion(self.correo_admin)
        if generada:
            print(f"\n  CUENTA DE ADMINISTRACIÓN CREADA\n"
                  f"  Correo: {self.correo_admin}\n"
                  f"  Clave:  {clave}\n"
                  f"  Guárdala ahora: no se vuelve a mostrar.\n")

    def _sala_publica(self, sala) -> dict:
        d = sala.a_dict()
        d["precio_texto"] = a_texto(sala.precio_carton)
        return d

    def _partida_de_sala(self, sala_id: str):
        """La partida abierta de una sala, sea o no la que está en pantalla.

        No toca la partida "actual" del servidor: sirve para mirar dentro de
        cualquier sala sin cambiar lo que están viendo los jugadores.
        """
        # Si esa sala tiene una partida viva en memoria, es esa. Reconstruirla
        # desde la base daría "ya existe", porque el objeto sigue cargado.
        for partida in self.mesa.sala.partidas.values():
            if partida.sala == sala_id and partida.estado != "terminada":
                return partida
        fila = self.almacen.partida_abierta_de(sala_id)
        if fila is None:
            return None
        return self._rehidratar(fila)

    def sala_viva(self, sala_id: str) -> dict:
        """Lo que se ve dentro de una sala: jugadores, cartones y bolas."""
        sala = self.salas.de(sala_id)
        with self.candado:
            partida = self._partida_de_sala(sala_id)
            if partida is None:
                return {"sala": self._sala_publica(sala), "jugadores": [], "bolas_sacadas": [],
                        "estado": "sin partida", "cartones": 0, "bote": 0, "bote_texto": a_texto(0)}
            jugadores = []
            for correo in partida.jugadores():
                cartones = []
                for cid in partida.cartones_de(correo):
                    c = partida.cartones[cid]
                    cartones.append({
                        "id": cid,
                        "numeros": [list(fila) for fila in c.numeros],
                        "marcados": sorted(f"{f}-{col}" for f, col in c.marcados),
                    })
                jugadores.append({
                    "correo": correo,
                    "cartones": len(cartones),
                    "detalle": cartones,
                    "premios": [g for g in partida.ganadores if g.get("jugador") == correo],
                })
            bote = partida.precio_carton * len(partida.cartones)
            return {
                "sala": self._sala_publica(sala),
                "id": partida.id,
                "estado": partida.estado,
                "patron": partida.patron,
                "jugadores": jugadores,
                "cartones": len(partida.cartones),
                "bolas_sacadas": list(partida.bombo.sacadas),
                "bote": bote,
                "bote_texto": a_texto(bote),
                "plazas": partida.plazas,
                "ganadores": list(partida.ganadores),
            }

    def partida(self, sala_id: str | None = None):
        """Devuelve la partida abierta de una sala, abriendo una nueva si no hay.

        Cada sala lleva su propia partida. Se apoya en la base de datos: si el
        servidor se reinicia en mitad de una partida, se recupera en vez de
        empezar de cero.
        """
        sala_id = sala_id or self._partida_sala
        with self.candado:
            self._partida_sala = sala_id
            partida = self.mesa.sala.partidas.get(self._partida_id) if self._partida_id else None
            if partida is None or partida.estado == "terminada" or partida.sala != sala_id:
                # Buscar en memoria antes de la base: si la partida sigue
                # cargada, rehidratarla lanzaría "ya existe".
                partida = self._partida_de_sala(sala_id)
                if partida is None:
                    partida = self._nueva_partida(sala_id)
                self._partida = partida
                self._partida_id = partida.id
            return partida

    def reabrir_partida(self, sala_id: str) -> None:
        """Tira la partida abierta de una sala para que coja el juego/precio nuevos.

        Se usa cuando el anfitrión cambia el tipo de juego o el precio de su sala
        de trabajo. Solo se descarta si todavía no se ha vendido ningún cartón, para
        no borrar una partida que ya está en marcha.
        """
        with self.candado:
            partida = self._partida_de_sala(sala_id)
            if partida is None or partida.cartones:
                return
            self.mesa.sala.partidas.pop(partida.id, None)
            self.almacen.borrar_partida(partida.id)
            if self._partida_id == partida.id:
                self._partida = None
                self._partida_id = ""

    def _nueva_partida(self, sala_id: str | None = None) -> object:
        """Abre una partida nueva en la sala indicada (o la de por defecto)."""
        sala = self.salas.de(sala_id or self._partida_sala)
        # El tipo de juego de la sala decide qué patrón se premia. Si la sala es
        # de jugador (o vieja) y no tiene tipo, se cae al modo de siempre.
        from bingo.cartones import MODOS, PATRONES
        patron = sala.tipo_juego if sala.tipo_juego in PATRONES else MODOS[sala.modo][0]
        # La sala decide cuántos puestos premia: 1 (un ganador) o varios (1º, 2º…).
        plazas = sala.plazas
        partida = self.mesa.sala.abrir_partida(sala.precio_carton / 100, patron=patron,
                                              sala=sala.id, plazas=plazas)
        self._guardar(partida)
        return partida

    def _rehidratar(self, fila) -> object:
        """Reconstruye una partida guardada, con sus cartones y sus bolas."""
        from bingo.cartones import Bombo, Carton

        claves = fila.keys()
        plazas = int(fila["plazas"]) if "plazas" in claves else 1
        partida = self.mesa.sala.abrir_partida(
            fila["precio_carton"] / 100, patron=fila["patron"], id_=fila["id"],
            sala=fila["sala"] or "", plazas=plazas,
        )
        partida.estado = fila["estado"]
        partida.ganador = fila["ganador"]
        partida.carton_ganador = fila["carton_ganador"]
        partida.premio = fila["premio"]
        partida.empezada = fila["empezada"]
        partida.terminada = fila["terminada"]
        crudo = fila["ganadores"] if "ganadores" in claves else ""
        if crudo:
            import json as _json
            try:
                partida.ganadores = _json.loads(crudo)
            except ValueError:
                partida.ganadores = []
        bolas = [int(n) for n in fila["bolas"].split(",") if n]
        partida.bombo.sacadas = list(bolas)
        partida.bombo.bolas = [n for n in range(1, 76) if n not in set(bolas)]
        for f in self.almacen.cartones(fila["id"]):
            numeros = tuple(tuple(int(x) for x in fila_n.split("|")) for fila_n in f["numeros"].split(";"))
            carton = Carton(numeros=numeros, id=f["id"])
            for bola in bolas:
                carton.marcar(bola)
            partida.cartones[carton.id] = carton
            partida.dueno[carton.id] = f["correo"]
        return partida

    def _guardar(self, partida) -> None:
        import json as _json
        self.almacen.guardar_partida({
            "id": partida.id, "sala": getattr(partida, "sala", ""),
            "patron": partida.patron, "precio_carton": partida.precio_carton,
            "estado": partida.estado, "bolas": ",".join(str(b) for b in partida.bombo.sacadas),
            "ganador": partida.ganador, "carton_ganador": partida.carton_ganador,
            "premio": partida.premio, "empezada": partida.empezada, "terminada": partida.terminada,
            "ganadores": _json.dumps(getattr(partida, "ganadores", []), ensure_ascii=False),
            "plazas": getattr(partida, "plazas", 1),
        })

    def guardar_carton(self, partida, carton_id: str) -> None:
        carton = partida.cartones[carton_id]
        numeros = ";".join("|".join(str(n) for n in fila) for fila in carton.numeros)
        self.almacen.guardar_carton(carton_id, partida.id, partida.dueno[carton_id], numeros)

    def resumen(self) -> dict:
        """Datos para el panel de administración."""
        usuarios = self.usuarios.usuarios()
        partidas = self.almacen.partidas(50)
        apostado = sum(f["precio_carton"] * len(self.almacen.cartones(f["id"])) for f in partidas)
        pagado = sum(f["premio"] for f in partidas)
        return {
            "usuarios": len(usuarios),
            "jugadores": sum(1 for u in usuarios if u.rol == "jugador"),
            "total_en_cuentas": self.monedero.total_en_cuentas(),
            "retiros_pendientes": len(self.retiros.pendientes()),
            "total_pendiente": self.retiros.total_pendiente(),
            "depositos_pendientes": len(self.depositos.pendientes()),
            "depositos_pendiente_centimos": self.depositos.total_pendiente(),
            "depositos_comision": self.depositos.comision_total(),
            "depositos_comision_texto": a_texto(self.depositos.comision_total()),
            "partidas": len(partidas),
            "apostado": apostado,
            "pagado": pagado,
            "margen": apostado - pagado,
            "economia": self._economia(),
            "salas": len(self.salas.todas()),
        }

    def _economia(self) -> dict:
        """La economía del bingo más lo que deja la comisión de depósitos."""
        eco = self.salas.economia()
        dep = self.depositos.comision_total()
        eco["depositos_comision"] = dep
        eco["depositos_comision_texto"] = a_texto(dep)
        eco["app_total"] = eco["app"] + dep
        eco["app_total_texto"] = a_texto(eco["app_total"])
        return eco


class Manejador(BaseHTTPRequestHandler):
    server_version = "BingoPiramide777/1.1"

    # Si la petición es HEAD no se escribe el cuerpo, solo las cabeceras.
    _cabeza = False

    @property
    def juego(self) -> Juego:
        return self.server.juego

    # -- utilidades --

    def _json(self, datos, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not self._cabeza:
            self.wfile.write(cuerpo)

    def _error(self, mensaje: str, codigo: int = 400) -> None:
        self._json({"error": mensaje}, codigo)

    def _leer_json(self) -> dict:
        # El tope cubre la foto de perfil: 300 KB en claro son ~400 KB en base64
        # más el envoltorio JSON. Un cuerpo mayor que esto se ignora.
        largo = int(self.headers.get("Content-Length") or 0)
        if largo <= 0 or largo > 600_000:
            return {}
        try:
            return json.loads(self.rfile.read(largo).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _token(self) -> str:
        cabecera = self.headers.get("Authorization") or ""
        return cabecera[7:].strip() if cabecera.startswith("Bearer ") else ""

    def _jugador(self) -> str | None:
        sesion = self.juego.usuarios.sesion(self._token())
        return sesion.correo if sesion else None

    def _fijar_pais(self, datos: dict | None = None) -> str:
        """Averigua el país de la petición: cuerpo > cabecera > idioma > por defecto.

        El frontend manda el país elegido (o el detectado por IP) para que la app
        muestre la moneda y el método de cobro correctos. Si no llega ninguno,
        vale Venezuela.
        """
        from nucleo import paises

        candidato = ""
        if isinstance(datos, dict) and datos.get("pais"):
            candidato = str(datos["pais"])
        if not candidato:
            candidato = self.headers.get("X-Pais") or self.headers.get("X-Country") or ""
        if not candidato:
            idioma = (self.headers.get("Accept-Language") or "").lower()
            if idioma.startswith("es-co"):
                candidato = "CO"
            elif idioma.startswith("es-cl"):
                candidato = "CL"
            # Cualquier otro idioma cae en Venezuela: es el país por defecto y no
            # conviene adivinar dólares solo porque el navegador esté en inglés.
        return paises.usar_pais(candidato)

    def _admin(self) -> str | None:
        jugador = self._jugador()
        return jugador if jugador and self.juego.usuarios.es_admin(jugador) else None

    def _estatico(self, ruta: str) -> None:
        nombre = "index.html" if ruta in ("/", "") else ruta.lstrip("/")
        if ".." in nombre or nombre.startswith("/"):
            self._error("Ruta no válida.", 400)
            return
        camino = os.path.join(RAIZ_WEB, nombre)
        if not os.path.isfile(camino):
            self._error("No encontrado.", 404)
            return
        tipos = {".html": "text/html", ".css": "text/css", ".js": "text/javascript",
                 ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
                 ".webp": "image/webp", ".ico": "image/x-icon"}
        ext = os.path.splitext(camino)[1].lower()
        with open(camino, "rb") as f:
            cuerpo = f.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{tipos.get(ext, 'application/octet-stream')}; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        # Sin caché: al cambiar el programa, el navegador tiene que traer la
        # versión nueva y no una vieja guardada.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not self._cabeza:
            self.wfile.write(cuerpo)

    def _deposito_json(self, d) -> dict:
        return {"id": d.id, "correo": d.correo, "centimos": d.centimos,
                "importe_texto": a_texto(d.centimos), "metodo": d.metodo,
                "referencia": d.referencia, "banco": d.banco, "dia": d.dia,
                "estado": d.estado, "nota": d.nota, "pedido": d.pedido,
                "revisado": d.revisado, "revisado_por": d.revisado_por,
                "pais": getattr(d, "pais", "VE"),
                "comision": getattr(d, "comision", 0),
                "comision_texto": a_texto(getattr(d, "comision", 0)),
                "acreditado": getattr(d, "acreditado", 0),
                "acreditado_texto": a_texto(getattr(d, "acreditado", 0))}

    def _sala_json(self, s) -> dict:
        d = s.a_dict()
        d["precio_texto"] = a_texto(s.precio_carton)
        return d

    def _jugador_json(self, correo: str) -> dict:
        """Datos públicos de un jugador para la mesa: nombre, foto y correo."""
        fila = self.juego.almacen.usuario(correo)
        nombre = (fila["nombre"] if fila and fila["nombre"] else "") or correo.split("@")[0]
        tiene_foto = bool(fila and (fila["foto"] or ""))
        return {
            "correo": correo,
            "nombre": nombre,
            "foto_url": f"/api/foto?correo={quote(correo)}" if tiene_foto else "",
        }

    def _enriquecer_mesa(self, vista: dict) -> dict:
        """Añade nombre y foto a la lista 'a cuánto están' de la mesa."""
        for fila in vista.get("a_cuanto_estan", []):
            fila.update(self._jugador_json(fila["jugador"]))
        return vista

    def _retiro_json(self, r) -> dict:
        return {"id": r.id, "correo": r.correo, "centimos": r.centimos,
                "importe_texto": a_texto(r.centimos), "metodo": r.metodo,
                "detalles": r.detalles, "estado": r.estado, "pedido": r.pedido,
                "revisado": r.revisado, "revisado_por": r.revisado_por, "nota": r.nota}

    # -- GET --

    def do_GET(self) -> None:  # noqa: N802
        ruta = urlparse(self.path).path
        self._fijar_pais()

        if ruta == "/api/salud":
            self._json({"estado": "bien", "servicio": "Bingo Pirámide 777"})
            return

        if ruta == "/api/sesion":
            # Quién es de verdad esta sesión. El navegador no se fía de lo que
            # tenga guardado: lo pregunta al servidor cada vez que arranca.
            jugador = self._jugador()
            if not jugador:
                self._error("Sin sesión.", 401)
                return
            datos_jugador = self._jugador_json(jugador)
            self._json({"correo": jugador,
                        "nombre": datos_jugador["nombre"],
                        "foto_url": datos_jugador["foto_url"],
                        "admin": self.juego.usuarios.es_admin(jugador)})
            return

        if ruta == "/api/foto":
            # Foto de perfil pública: se sirve como imagen desde la base de datos.
            correo = (parse_qs(urlparse(self.path).query).get("correo") or [""])[0]
            correo = correo.strip().lower()
            foto = self.juego.usuarios.foto_de(correo) if correo else ""
            if not foto:
                self._error("Ese jugador no tiene foto.", 404)
                return
            try:
                cabecera, datos_b64 = foto.split(",", 1)
                contenido = base64.b64decode(datos_b64)
                tipo = cabecera.split(";")[0].replace("data:", "") or "image/png"
            except (ValueError, IndexError):
                self._error("La foto está dañada.", 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(contenido)))
            self.send_header("Cache-Control", "public, max-age=60")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not self._cabeza:
                self.wfile.write(contenido)
            return

        if ruta == "/api/partida":
            with self.juego.candado:
                vista = self.juego.mesa.partida_publica(self.juego.partida().id)
                self._enriquecer_mesa(vista)
                try:
                    vista["fecha_partida"] = self.juego.salas.de(vista.get("sala") or None).fecha_partida
                except Exception:  # noqa: BLE001
                    vista["fecha_partida"] = ""
                self._json(vista)
            return

        if ruta == "/api/salas":
            with self.juego.candado:
                # Solo las públicas: las privadas se comparten con su enlace, que
                # lleva el id. Así una sala privada no se cuela en el listado.
                salas = [s for s in self.juego.salas.publicas() if s.activa]
            self._json({"salas": [self._sala_json(s) for s in salas]})
            return

        if ruta == "/api/evento":
            with self.juego.candado:
                self._json(self.juego.info_evento())
            return

        if ruta == "/api/ganadores":
            # Escaparate público: los últimos que cantaron bingo. Se muestran
            # sin sesión, así que solo sale el nombre corto, nunca el correo.
            with self.juego.candado:
                filas = self.juego.almacen.ganadores_recientes(12)
            self._json({"ganadores": [
                {"nombre": f["nombre"], "sala": f["sala"],
                 "premio": f["premio"], "premio_texto": a_texto(f["premio"]),
                 "cuando": f["cuando"]}
                for f in filas]})
            return

        if ruta == "/api/mis-salas":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                salas = self.juego.salas.de_dueno(jugador)
                ganancias = self.juego.salas.ganancias(jugador)
            self._json({"salas": [self._sala_json(s) for s in salas], "ganancias": ganancias})
            return

        if ruta == "/api/referidos":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                # Cuentas de antes de los referidos: se les da código al vuelo.
                self.juego.usuarios.asegurar_codigo_amigo(jugador)
                resumen = self.juego.referidos.resumen(jugador)
            self._json({"ok": True, **resumen})
            return

        if ruta == "/api/invitacion":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                # Todas las cuentas tienen su código de invitación a la sala de
                # trabajo: se genera al vuelo la primera vez.
                codigo = self.juego.usuarios.asegurar_codigo_invitacion(jugador)
                sala = self.juego.salas.de(SALA_CASA_ID)
                invitados = self.juego.almacen.invitados_de_invitacion(jugador)
            self._json({
                "ok": True,
                "codigo": codigo,
                "sala": SALA_CASA_ID,
                "sala_nombre": sala.nombre if sala else SALA_CASA_NOMBRE,
                "invitados": len(invitados),
                "detalle": [{"invitado": i} for i in invitados],
                "premio_pct": 80,
                "anfitrion_pct": 15,
                "app_pct": 5,
            })
            return

        if ruta == "/api/config":
            from nucleo.usuarios import PREGUNTAS
            from nucleo import paises as _paises
            from bingo.cartones import MODOS, TIPOS_JUEGO
            pais = _paises.pais_actual()
            metodo = _paises.metodo_de_pais(pais)
            self._json({
                "preguntas": list(PREGUNTAS),
                "modos": list(MODOS),
                "tipos_juego": [{"id": i, "nombre": n} for i, n in TIPOS_JUEGO],
                "metodos_deposito": list(METODOS_DEPOSITO),
                "deposito_minimo_texto": a_texto(self.juego.depositos.config.minimo),
                "deposito_tope_texto": a_texto(self.juego.depositos.config.tope_diario),
                "retiro_minimo": self.juego.retiros.config.minimo,
                "retiro_minimo_texto": a_texto(self.juego.retiros.config.minimo),
                "retiro_tope_texto": a_texto(self.juego.retiros.config.tope_diario),
                "metodos": list(self.juego.retiros.config.metodos),
                # Multi-país: el país activo, la moneda y el método de cobro.
                "pais": pais,
                "moneda": _paises.moneda_de(pais),
                "simbolo": _paises.simbolo_de(pais),
                "metodo_pago": metodo.a_dict() if metodo else None,
                "metodos_pago": [m.a_dict() for m in _paises.metodos_de_pais(pais)],
                "catalogo_paises": _paises.catalogo(),
                "cuentas_admin": [c.a_dict() for c in _paises.cuentas_admin()],
                "pais_base": _paises.PAIS_BASE,
                "tasas": _paises.tasas(),
            })
            return

        if ruta == "/api/paises":
            from nucleo import paises as _paises
            self._json(_paises.catalogo())
            return

        if ruta == "/api/idiomas":
            from nucleo import idiomas as _idiomas
            # El idioma se detecta igual que el país: lo elegido manda; si no,
            # lo que pide el navegador en Accept-Language.
            elegido = _idiomas.detectar(self.headers.get("Accept-Language"))
            self._json({**_idiomas.catalogo(), "idioma_actual": elegido})
            return

        if ruta == "/api/datos-cobro":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                ficha = self.juego.fichas.de(jugador)
            self._json({"ficha": ficha.a_dict(), "metodos": list(_METODOS_COBRO),
                        "campos": {m: [{"key": k, "label": v} for k, v in cs]
                                   for m, cs in _CAMPOS_COBRO.items()}})
            return

        if ruta == "/api/billetera":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                billetera = self.juego.billeteras.de(jugador)
            self._json({"billetera": billetera, "redes": REDES_BILLETERA})
            return

        if ruta == "/api/saldo":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                saldo = self.juego.monedero.saldo(jugador)
                self._json({"saldo": saldo, "saldo_texto": a_texto(saldo),
                            "admin": self.juego.usuarios.es_admin(jugador)})
            return

        if ruta == "/api/historial":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                movs = [{"tipo": m.tipo, "centimos": m.centimos, "motivo": m.motivo,
                         "saldo": m.saldo_despues, "cuando": m.cuando}
                        for m in self.juego.monedero.historial(jugador, 50)]
            self._json({"movimientos": movs})
            return

        if ruta == "/api/depositos":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                lista = [self._deposito_json(d) for d in self.juego.depositos.listar(correo=jugador)]
            self._json({"depositos": lista})
            return

        if ruta == "/api/estadisticas":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                r = self.juego.almacen.resumen_jugador(jugador)
                ranking = self.juego.almacen.ranking(20)
                # El puesto del jugador en el ranking, si aparece.
                puesto = next((i + 1 for i, f in enumerate(ranking)
                               if f["correo"] == jugador), None)
            self._json({
                "jugador": {
                    "correo": jugador,
                    "cartones": r["cartones"],
                    "partidas": r["partidas"],
                    "premios_ganados": r["premios_ganados"],
                    "total_apostado": r["total_apostado"],
                    "total_apostado_texto": a_texto(r["total_apostado"]),
                    "total_ganado": r["total_ganado"],
                    "total_ganado_texto": a_texto(r["total_ganado"]),
                    "neto": r["total_ganado"] - r["total_apostado"],
                    "neto_texto": a_texto(r["total_ganado"] - r["total_apostado"]),
                    "puesto": puesto,
                },
                "ranking": [
                    {"puesto": i + 1, "correo": f["correo"], "ganado": f["ganado"],
                     "ganado_texto": a_texto(f["ganado"]), "premios": f["premios"]}
                    for i, f in enumerate(ranking)
                ],
            })
            return

        if ruta == "/api/retiros":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                lista = [self._retiro_json(r) for r in self.juego.retiros.listar(correo=jugador)]
            self._json({"retiros": lista})
            return

        # --- administración ---

        if ruta == "/api/admin/resumen":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            with self.juego.candado:
                self._json(self.juego.resumen())
            return

        if ruta == "/api/admin/salas":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            with self.juego.candado:
                salas = self.juego.salas.todas(incluir_inactivas=True)
                economia = self.juego.salas.economia()
                evento = self.juego.info_evento()
            self._json({"salas": [self._sala_json(s) for s in salas], "economia": economia,
                        "evento": evento})
            return

        if ruta == "/api/admin/sala":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            qs = parse_qs(urlparse(self.path).query)
            sala_id = qs["sala"][0] if qs.get("sala") else ""
            if not sala_id:
                self._error("Falta la sala.")
                return
            try:
                self._json(self.juego.sala_viva(sala_id))
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/admin/jugadores":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            with self.juego.candado:
                lista = [{"correo": u.correo, "nombre": u.nombre, "rol": u.rol,
                          "activo": u.activo, "creado": u.creado,
                          "verificado": u.verificado,
                          "pregunta": bool(self.juego.usuarios.pregunta_de(u.correo)),
                          "comision_pct": u.comision_pct,
                          "comision_texto": (f"{u.comision_pct} %" if u.comision_pct >= 0
                                             else "10 % (por defecto)"),
                          "saldo": self.juego.monedero.saldo(u.correo),
                          "saldo_texto": a_texto(self.juego.monedero.saldo(u.correo))}
                         for u in self.juego.usuarios.usuarios()]
            self._json({"jugadores": lista})
            return

        if ruta == "/api/admin/movimientos":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            with self.juego.candado:
                filas = self.juego.almacen.todos_los_movimientos(200)
            self._json({"movimientos": [
                {"correo": f["correo"], "tipo": f["tipo"], "centimos": f["centimos"],
                 "importe_texto": a_texto(f["centimos"]), "saldo_despues": f["saldo_despues"],
                 "motivo": f["motivo"], "cuando": f["cuando"]} for f in filas]})
            return

        if ruta == "/api/admin/partidas":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            with self.juego.candado:
                filas = self.juego.almacen.partidas(50)
                salida = []
                for f in filas:
                    cartones = self.juego.almacen.cartones(f["id"])
                    salida.append({
                        "id": f["id"], "patron": f["patron"], "estado": f["estado"],
                        "precio_carton": f["precio_carton"], "cartones": len(cartones),
                        "bolas": len([n for n in f["bolas"].split(",") if n]),
                        "ganador": f["ganador"], "premio": f["premio"],
                        "premio_texto": a_texto(f["premio"]),
                        "apostado": f["precio_carton"] * len(cartones),
                        "apostado_texto": a_texto(f["precio_carton"] * len(cartones)),
                    })
            self._json({"partidas": salida})
            return

        if ruta == "/api/admin/depositos":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            qs = parse_qs(urlparse(self.path).query)
            estado = qs["estado"][0] if qs.get("estado") else None
            with self.juego.candado:
                lista = [self._deposito_json(d) for d in self.juego.depositos.listar(estado=estado)]
            self._json({"depositos": lista})
            return

        if ruta == "/api/admin/glenis":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            with self.juego.candado:
                filas = self.juego.almacen.historial_glenis(40)
            self._json({
                "configurada": self.juego.glenis.configurada,
                "historial": [{"quien": f["quien"], "texto": f["texto"], "cuando": f["cuando"]}
                              for f in reversed(filas)],
            })
            return

        if ruta == "/api/admin/retiros":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            estado = None
            qs = parse_qs(urlparse(self.path).query)
            if qs.get("estado"):
                estado = qs["estado"][0]
            with self.juego.candado:
                lista = [self._retiro_json(r) for r in self.juego.retiros.listar(estado=estado)]
            self._json({"retiros": lista})
            return

        if ruta == "/api/admin/referidos":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            with self.juego.candado:
                filas = self.juego.almacen.referidos(500)
                total = sum(int(f["centimos"]) for f in filas)
                self._json({"referidos": [
                    {"partida": f["partida"], "referido": f["referido"],
                     "padrino": f["padrino"], "centimos": f["centimos"],
                     "texto": a_texto(f["centimos"]), "cuando": f["cuando"]}
                    for f in filas],
                    "total": total, "total_texto": a_texto(total),
                    "pct": self.juego.referidos.porcentaje(),
                    "economia_pais": self.juego.salas.economia_por_pais().get("paises", [])})
            return

        if ruta == "/api/admin/cobros":
            # El sistema de cobro completo: qué se cobra, cuánto se ha cobrado y
            # si algún cobro se ha hecho dos veces (auditoría).
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            with self.juego.candado:
                self._json(self.juego.cobros.resumen())
            return

        if ruta == "/admin":
            self._estatico("admin.html")
            return

        self._estatico(ruta)

    def do_HEAD(self) -> None:  # noqa: N802
        # Mismo trato que GET pero sin cuerpo: lo usan los monitores de
        # disponibilidad y las vistas previas de enlaces.
        self._cabeza = True
        try:
            self.do_GET()
        finally:
            self._cabeza = False

    # -- POST --

    def do_POST(self) -> None:  # noqa: N802
        ruta = urlparse(self.path).path
        datos = self._leer_json()
        self._fijar_pais(datos)

        if ruta == "/api/registro":
            try:
                # Si hay correo configurado, la cuenta nace sin verificar y se le
                # manda un código. Sin correo configurado no se puede verificar a
                # nadie, así que la cuenta se crea lista para entrar (y se avisa).
                exige_verificacion = self.juego.correo.configurado
                with self.juego.candado:
                    self.juego.usuarios.registrar(
                        datos.get("correo", ""), datos.get("clave", ""),
                        datos.get("nombre", ""), "jugador",
                        datos.get("pregunta", ""), datos.get("respuesta", ""),
                        verificado=not exige_verificacion,
                        codigo_amigo=datos.get("codigo_amigo", ""),
                        codigo_invitacion=datos.get("codigo_invitacion", ""))
                    enviado = False
                    if exige_verificacion:
                        codigo = self.juego.usuarios.pedir_codigo_verificacion(
                            datos.get("correo", ""))
                        if codigo:
                            try:
                                enviado = self.juego.correo.enviar_verificacion(
                                    datos.get("correo", "").strip().lower(), codigo, 15)
                            except ErrorDeCorreo:
                                enviado = False
                self._json({"ok": True, "verificacion_requerida": exige_verificacion,
                            "codigo_enviado": enviado,
                            "mensaje": ("Cuenta creada. Te hemos enviado un código al correo "
                                        "para confirmarla." if exige_verificacion
                                        else "Cuenta creada. Ya puedes entrar.")})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/verificar":
            try:
                with self.juego.candado:
                    self.juego.usuarios.confirmar_correo(datos.get("correo", ""),
                                                         datos.get("codigo", ""))
                self._json({"ok": True, "mensaje": "Correo confirmado. Ya puedes entrar."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/verificar/reenviar":
            try:
                with self.juego.candado:
                    codigo = self.juego.usuarios.pedir_codigo_verificacion(datos.get("correo", ""))
                    enviado = False
                    if codigo:
                        try:
                            enviado = self.juego.correo.enviar_verificacion(
                                datos.get("correo", "").strip().lower(), codigo, 15)
                        except ErrorDeCorreo:
                            enviado = False
                self._json({"ok": True, "enviado": enviado,
                            "mensaje": "Te hemos enviado un código nuevo."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/entrar":
            try:
                with self.juego.candado:
                    sesion = self.juego.usuarios.entrar(datos.get("correo", ""), datos.get("clave", ""))
                    admin = self.juego.usuarios.es_admin(sesion.correo)
                self._json({"ok": True, "token": sesion.token, "caduca": sesion.caduca,
                            "correo": sesion.correo, "admin": admin})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc), 401)
            return

        if ruta == "/api/salir":
            self.juego.usuarios.salir(self._token())
            self._json({"ok": True})
            return

        if ruta == "/api/recargar":
            # Solo la administración ingresa saldo a mano. El dinero de verdad
            # entra por los depósitos, que se revisan y se aprueban. Sin esto,
            # cualquiera se ponía el saldo que quisiera.
            if not self._admin():
                self._error("Solo la administración puede ingresar saldo. "
                            "Usa un depósito para recargar.", 403)
                return
            try:
                correo = (datos.get("correo") or "").strip().lower()
                if correo and not self.juego.usuarios.usuario(correo):
                    raise ErrorDeMonedero("Ese usuario no existe.")
                centimos = a_centimos(datos.get("importe", ""))
                if centimos <= 0:
                    raise ErrorDeDinero("El importe tiene que ser mayor que cero.")
                with self.juego.candado:
                    destino = correo or self._jugador()
                    self.juego.monedero.recargar(destino, centimos, "ingreso de administración")
                    saldo = self.juego.monedero.saldo(destino)
                self._json({"ok": True, "saldo": saldo, "saldo_texto": a_texto(saldo)})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/sala/crear":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    sala = self.juego.salas.crear(
                        jugador, datos.get("nombre", ""), datos.get("modo", ""),
                        datos.get("precio", ""), datos.get("publica", True),
                        puestos=datos.get("puestos", 1),
                        premios_pct=datos.get("premios_pct"))
                if sala.reparte_varios_puestos:
                    mensaje = (f"Sala {sala.nombre} creada. Reparte el bote entre 1º, 2º y 3º; "
                               "tú cobras el 10% de los botes.")
                else:
                    mensaje = (f"Sala {sala.nombre} creada. El ganador cobra el 70% y tú "
                               "cobras el 10% de los botes.")
                self._json({"ok": True, "sala": self._sala_json(sala), "mensaje": mensaje})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/sala/cerrar":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    sala = self.juego.salas.cerrar(
                        datos.get("sala", ""), jugador, self.juego.usuarios.es_admin(jugador))
                self._json({"ok": True, "sala": self._sala_json(sala)})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/sala/entrar":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    sala = self.juego.salas.de(datos.get("sala", ""))
                    if not sala.activa:
                        raise ErrorDeSalas("Esa sala está cerrada.")
                    partida = self.juego.partida(sala.id)
                    vista = self.juego.mesa.partida_publica(partida.id)
                    self._enriquecer_mesa(vista)
                    vista["sala_nombre"] = sala.nombre
                    vista["modo"] = sala.modo
                    vista["es_evento"] = sala.es_evento
                    vista["es_trabajo"] = sala.es_trabajo
                    vista["dueno"] = sala.dueno
                    vista["soy_dueno"] = bool(sala.dueno and sala.dueno == jugador)
                    vista["max_cartones"] = sala.max_cartones
                    vista["reparto"] = self.juego.salas.reparto_de_sala(
                        sala.id, partida.precio_carton * len(partida.cartones))
                    if sala.es_evento:
                        vista["evento"] = self.juego.info_evento()
                self._json({"ok": True, "partida": vista})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/sala/trabajo":
            # El anfitrión de una sala de trabajo decide el juego y el precio del
            # cartón. Solo él (el dueño) puede tocar su sala.
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    sala = self.juego.salas.configurar_trabajo(
                        datos.get("sala", ""), jugador,
                        precio=datos.get("precio"),
                        tipo_juego=datos.get("tipo_juego"),
                        fecha_partida=datos.get("fecha_partida"))
                    # La partida abierta coge el juego y el precio nuevos.
                    self.juego.reabrir_partida(sala.id)
                self._json({"ok": True, "sala": self._sala_json(sala),
                            "mensaje": f"Sala {sala.nombre} actualizada."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/carton":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                # Se pueden comprar varios cartones de una vez (1 a 10).
                cuantos = datos.get("cantidad", 1)
                try:
                    cuantos = int(cuantos)
                except (TypeError, ValueError):
                    cuantos = 1
                cuantos = max(1, min(cuantos, 10))
                with self.juego.candado:
                    partida = self.juego.partida(datos.get("sala") or None)
                    # Aforo: cuántos jugadores distintos caben. Cupo: cuántos cartones.
                    self.juego.comprobar_aforo(partida, jugador)
                    # Tope por jugador: se comprueba antes de comprar nada, para no
                    # dejar media compra hecha si se pasa del máximo.
                    self.juego.comprobar_max_cartones(partida, jugador, cuantos)
                    comprados = []
                    for _ in range(cuantos):
                        self.juego.comprobar_cupo(partida)
                        carton_id, precio = self.juego.mesa.comprar_carton(partida.id, jugador)
                        carton = partida.cartones[carton_id]
                        self.juego.guardar_carton(partida, carton_id)
                        comprados.append({"carton": carton_id, "numeros": carton.numeros})
                    self.juego._guardar(partida)
                    saldo = self.juego.monedero.saldo(jugador)
                primero = comprados[0]
                self._json({"ok": True, "carton": primero["carton"],
                            "numeros": primero["numeros"],
                            "cartones": comprados, "cantidad": len(comprados),
                            "precio": precio, "precio_texto": a_texto(precio),
                            "precio_total_texto": a_texto(precio * len(comprados)),
                            "saldo": saldo})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/bola":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    partida = self.juego.partida(datos.get("sala") or None)
                    if partida.abierta:
                        self.juego.mesa.sala.empezar(partida.id)
                    bola = self.juego.mesa.sala.sacar_bola(partida.id)
                    bolas = list(partida.bombo.sacadas)
                    if partida.bombo.quedan() == 0:
                        self.juego.mesa.sala.cerrar_a_mano(partida.id)
                    self.juego._guardar(partida)
                self._json({"ok": True, "bola": bola, "bolas": bolas,
                            "sin_bolas": partida.bombo.quedan() == 0})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/bingo":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    partida = self.juego.partida(datos.get("sala") or None)
                    res = self.juego.mesa.resolver_cantada(partida.id, jugador, datos.get("carton", ""))
                    # El premio de la partida es la suma de todos los puestos.
                    partida.premio = sum(res.get("premios") or [res["premio"]])
                    # Los padrinos de los ganadores cobran su parte de la app.
                    # Se liquida puesto a puesto: la parte de la app ya está
                    # calculada en el reparto, así que no se toca el 80/10/10.
                    self.juego.referidos.liquidar(
                        partida.id, list(partida.ganadores), res, self.juego.monedero)
                    self.juego._guardar(partida)
                    res["premio_texto"] = a_texto(res["premio"])
                    res["nombre_puesto"] = NOMBRES_PUESTO[res["puesto"] - 1] \
                        if res["puesto"] <= len(NOMBRES_PUESTO) else f'{res["puesto"]}º'
                    res["saldo"] = self.juego.monedero.saldo(jugador)
                self._json({"ok": True, **res})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/deposito":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    d = self.juego.depositos.declarar(
                        jugador, datos.get("importe", ""), datos.get("referencia", ""),
                        datos.get("banco", ""), datos.get("dia", ""),
                        datos.get("metodo", "paypal"), datos.get("nota", ""),
                        datos.get("pais", ""))
                self._json({"ok": True, "deposito": self._deposito_json(d),
                            "mensaje": "Depósito declarado. Lo revisamos y te lo acreditamos."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/retiro":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    retiro = self.juego.retiros.pedir(jugador, datos.get("importe", ""),
                                                      datos.get("metodo", ""), datos.get("detalles", ""))
                    saldo = self.juego.monedero.saldo(jugador)
                self._json({"ok": True, "retiro": self._retiro_json(retiro),
                            "saldo": saldo, "saldo_texto": a_texto(saldo)})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/datos-cobro":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    ficha = self.juego.fichas.guardar(
                        jugador, datos.get("metodo", ""), datos.get("campos", {}))
                self._json({"ok": True, "ficha": ficha.a_dict()})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/billetera/desafio":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    reto = self.juego.billeteras.desafio(jugador)
                self._json({"ok": True, **reto})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/billetera":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    billetera = self.juego.billeteras.vincular(
                        jugador, datos.get("direccion", ""), datos.get("firma", ""),
                        datos.get("red", ""))
                self._json({"ok": True, "billetera": billetera,
                            "mensaje": "Billetera vinculada a tu cuenta."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/billetera/borrar":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                self.juego.billeteras.borrar(jugador)
            self._json({"ok": True, "mensaje": "Billetera desvinculada."})
            return

        if ruta == "/api/foto":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            if "foto" not in datos:
                # Si el cuerpo llegó vacío o demasiado grande, mejor avisar que
                # borrar la foto sin querer.
                self._error("No llegó la imagen. Prueba con una foto más pequeña.")
                return
            try:
                with self.juego.candado:
                    guardada = self.juego.usuarios.cambiar_foto(jugador, datos.get("foto", ""))
                self._json({"ok": True, "foto_url": self._jugador_json(jugador)["foto_url"],
                            "mensaje": "Foto guardada." if guardada else "Foto quitada."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/recuperar/pregunta":
            pregunta = self.juego.usuarios.pregunta_de(datos.get("correo", ""))
            # Si no hay pregunta, se responde igual y el paso siguiente fallará.
            # Así nadie usa esta pantalla para averiguar qué correos existen.
            self._json({"ok": True, "pregunta": pregunta or "Escribe tu correo y pide un código."})
            return

        if ruta == "/api/recuperar/pregunta/cambiar":
            try:
                with self.juego.candado:
                    self.juego.usuarios.cambiar_con_respuesta(
                        datos.get("correo", ""), datos.get("respuesta", ""), datos.get("clave", ""))
                self._json({"ok": True, "mensaje": "Contraseña cambiada. Ya puedes entrar."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/recuperar/codigo":
            try:
                with self.juego.candado:
                    codigo = self.juego.usuarios.pedir_codigo(datos.get("correo", ""))
                    enviado = False
                    if codigo:
                        try:
                            enviado = self.juego.correo.enviar_codigo(
                                datos.get("correo", "").strip().lower(), codigo, 15)
                        except ErrorDeCorreo:
                            enviado = False
                # Respuesta siempre igual: no se revela si el correo existe.
                self._json({"ok": True, "enviado": enviado,
                            "mensaje": "Si ese correo tiene cuenta, te hemos enviado un código."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/recuperar/codigo/cambiar":
            try:
                with self.juego.candado:
                    self.juego.usuarios.cambiar_con_codigo(
                        datos.get("correo", ""), datos.get("codigo", ""), datos.get("clave", ""))
                self._json({"ok": True, "mensaje": "Contraseña cambiada. Ya puedes entrar."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        # --- administración ---

        if ruta == "/api/admin/retiro":
            admin = self._admin()
            if not admin:
                self._error("Solo para administración.", 403)
                return
            accion = datos.get("accion")
            id_ = datos.get("id", "")
            nota = datos.get("nota", "")
            try:
                with self.juego.candado:
                    if accion == "pagar":
                        retiro = self.juego.retiros.pagar(id_, admin, nota)
                    elif accion == "rechazar":
                        retiro = self.juego.retiros.rechazar(id_, admin, nota)
                    else:
                        raise ErrorDeRetiro("Acción no válida (usa 'pagar' o 'rechazar').")
                self._json({"ok": True, "retiro": self._retiro_json(retiro)})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/admin/deposito":
            admin = self._admin()
            if not admin:
                self._error("Solo para administración.", 403)
                return
            accion = datos.get("accion")
            id_ = datos.get("id", "")
            nota = datos.get("nota", "")
            try:
                with self.juego.candado:
                    if accion == "acreditar":
                        d = self.juego.depositos.acreditar(id_, admin, nota)
                    elif accion == "rechazar":
                        d = self.juego.depositos.rechazar(id_, admin, nota)
                    else:
                        raise ErrorDeDeposito("Acción no válida (usa 'acreditar' o 'rechazar').")
                self._json({"ok": True, "deposito": self._deposito_json(d)})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/admin/glenis":
            admin = self._admin()
            if not admin:
                self._error("Solo para administración.", 403)
                return
            mensaje = (datos.get("mensaje") or "").strip()
            if not mensaje:
                self._error("Escribe algo.")
                return
            try:
                historial = [m for m in (datos.get("historial") or [])
                             if isinstance(m, dict) and m.get("content")]
                # El mensaje del administrador tiene que llegar a la IA. Si el
                # cliente ya lo incluyó en el historial, no se repite.
                if not (historial and historial[-1].get("role") == "user"
                        and historial[-1].get("content") == mensaje):
                    historial.append({"role": "user", "content": mensaje})
                with self.juego.candado:
                    respuesta = self.juego.glenis.conversar(historial, nombre_admin=admin)
                    self.juego.almacen.anotar_glenis(
                        f"g-{secrets.token_hex(8)}", admin, mensaje,
                        json.dumps(respuesta.acciones, ensure_ascii=False, default=str), time.time())
                    self.juego.almacen.anotar_glenis(
                        f"g-{secrets.token_hex(8)}", "Glenis IA", respuesta.texto, "", time.time())
                self._json({"ok": True, "respuesta": respuesta.texto,
                            "acciones": respuesta.acciones, "pasos": respuesta.pasos})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/admin/ajuste":
            admin = self._admin()
            if not admin:
                self._error("Solo para administración.", 403)
                return
            try:
                correo = (datos.get("correo") or "").strip().lower()
                if not self.juego.usuarios.usuario(correo):
                    raise ErrorDeMonedero("Ese usuario no existe.")
                centimos = a_centimos(datos.get("importe", ""))
                if datos.get("signo") == "restar":
                    centimos = -centimos
                with self.juego.candado:
                    self.juego.monedero.ajustar(correo, centimos, f"ajuste de {admin}")
                    saldo = self.juego.monedero.saldo(correo)
                self._json({"ok": True, "saldo": saldo, "saldo_texto": a_texto(saldo)})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/admin/restablecer":
            admin = self._admin()
            if not admin:
                self._error("Solo para administración.", 403)
                return
            try:
                correo = (datos.get("correo") or "").strip().lower()
                if not self.juego.usuarios.usuario(correo):
                    raise ErrorDeRetiro("Ese usuario no existe.")
                clave = (datos.get("clave") or "").strip()
                if not clave:
                    # Clave temporal legible, para pasársela al jugador.
                    clave = "Pepa-" + secrets.token_hex(3)
                with self.juego.candado:
                    self.juego.usuarios.restablecer_por_admin(correo, clave)
                self._json({"ok": True, "clave": clave,
                            "mensaje": "Contraseña cambiada y sesiones cerradas. Pásasela al jugador."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/admin/sala/editar":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            try:
                with self.juego.candado:
                    sala = self.juego.salas.configurar_sala(
                        datos.get("sala") or "",
                        precio=datos.get("precio"),
                        nombre=datos.get("nombre"),
                        activa=datos.get("activa"),
                        tipo_juego=datos.get("tipo_juego"),
                        cupo_cartones=datos.get("cupo_cartones"),
                        max_cartones=datos.get("max_cartones"),
                        fecha_partida=datos.get("fecha_partida"),
                    )
                self._json({"ok": True, "sala": self._sala_json(sala),
                            "mensaje": f"Sala {sala.nombre} actualizada."})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/admin/evento":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            try:
                with self.juego.candado:
                    sala = self.juego.salas.configurar_evento(
                        precio=datos.get("precio"),
                        aforo=datos.get("aforo"),
                        premios_pct=datos.get("premios_pct"),
                        activa=datos.get("activa"),
                        nombre=datos.get("nombre"),
                        tipo_juego=datos.get("tipo_juego"),
                        cupo_cartones=datos.get("cupo_cartones"),
                        max_cartones=datos.get("max_cartones"),
                        fecha_partida=datos.get("fecha_partida"),
                        ganadores=datos.get("ganadores"),
                    )
                    # La partida abierta coge los puestos y el precio nuevos, pero
                    # solo si todavía no se ha vendido ningún cartón.
                    self.juego.reabrir_partida(sala.id)
                    info = self.juego.info_evento()
                self._json({"ok": True, "evento": info, "sala": self._sala_json(sala)})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/admin/datos-cobro":
            admin = self._admin()
            if not admin:
                self._error("Solo para administración.", 403)
                return
            qs = parse_qs(urlparse(self.path).query)
            correo = (qs.get("correo") or [""])[0].strip().lower()
            if not correo:
                self._error("Falta el correo del jugador.")
                return
            try:
                with self.juego.candado:
                    ficha = self.juego.fichas.de(correo)
                    u = self.juego.usuarios.usuario(correo)
                self._json({"ficha": ficha.a_dict(),
                            "jugador": {"correo": correo,
                                        "nombre": (u.nombre if u else ""),
                                        "saldo": a_texto(self.juego.monedero.saldo(correo))}})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/admin/usuario":
            admin = self._admin()
            if not admin:
                self._error("Solo para administración.", 403)
                return
            try:
                correo = (datos.get("correo") or "").strip().lower()
                if correo == admin and "activo" in datos:
                    raise ErrorDeRetiro("No puedes desactivar tu propia cuenta.")
                if "activo" in datos:
                    self.juego.usuarios.activar(correo, bool(datos["activo"]))
                if "comision_pct" in datos:
                    crudo = datos["comision_pct"]
                    try:
                        pct = int(crudo)
                    except (TypeError, ValueError):
                        raise ErrorDeRetiro("El porcentaje tiene que ser un número entero.")
                    self.juego.usuarios.fijar_comision(correo, pct)
                self._json({"ok": True})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        self._error("Ruta no encontrada.", 404)

    def log_message(self, formato: str, *args) -> None:
        if "/api/" not in (formato % args):
            super().log_message(formato, *args)


def crear_servidor(host: str = "0.0.0.0", puerto: int = 8000, juego: Juego | None = None) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer((host, puerto), Manejador)
    servidor.juego = juego or Juego()
    return servidor


def main() -> None:
    puerto = int(os.environ.get("PORT", "8000"))
    servidor = crear_servidor(puerto=puerto)
    print(f"Bingo Pirámide 777 escuchando en http://0.0.0.0:{puerto}")
    print(f"Base de datos: {servidor.juego.almacen.ruta}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando…")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
