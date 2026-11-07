"""Servidor web de Bingo Pirámide 777.

Solo biblioteca estándar: http.server y sqlite3. Sin dependencias que instalar.
Sirve la interfaz del jugador, el panel de administración y la API.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from bingo import MesaBingo, Sala
from nucleo import Almacen, ErrorDeDinero, ErrorDeMonedero, Monedero, Usuarios, a_centimos, a_texto
from nucleo.retiros import ErrorDeRetiro, Retiros

RAIZ_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
CORREO_ADMIN_POR_DEFECTO = "bingopiramide777@gmail.com"


class Juego:
    """Estado de la aplicación: base de datos, usuarios, monedero, bingo y retiros.

    Un candado protege el dinero. Es un servidor pequeño, y así el saldo nunca se
    descuadra por dos peticiones que entren a la vez.
    """

    def __init__(self, almacen: Almacen | None = None, correo_admin: str | None = None,
                 clave_admin: str | None = None) -> None:
        self.candado = threading.RLock()
        self.almacen = almacen or Almacen(os.environ.get("BINGO_DB", "bingo777.db"))
        self.usuarios = Usuarios(self.almacen)
        self.monedero = Monedero(self.almacen)
        self.retiros = Retiros(self.almacen, self.monedero)
        self.mesa = MesaBingo(sala=Sala(), monedero=self.monedero)
        self._partida = None
        self.correo_admin = (correo_admin or os.environ.get("BINGO_ADMIN_EMAIL")
                             or CORREO_ADMIN_POR_DEFECTO)
        self.clave_admin = clave_admin or os.environ.get("BINGO_ADMIN_CLAVE") or ""
        self._crear_admin()

    def _crear_admin(self) -> None:
        """Crea la cuenta de administración si no existe.

        Si no hay clave configurada, se genera una y se muestra una sola vez por
        consola. Es mejor una clave aleatoria que una por defecto que todos saben.
        """
        if self.usuarios.usuario(self.correo_admin):
            return
        clave = self.clave_admin
        generada = False
        if not clave:
            clave = secrets.token_urlsafe(12)
            generada = True
        self.usuarios.asegurar_admin(self.correo_admin, clave)
        if generada:
            print(f"\n  CUENTA DE ADMINISTRACIÓN CREADA\n"
                  f"  Correo: {self.correo_admin}\n"
                  f"  Clave:  {clave}\n"
                  f"  Guárdala ahora: no se vuelve a mostrar.\n")

    def partida(self):
        """Devuelve la partida abierta, abriendo una nueva si no hay.

        Se apoya en la base de datos: si el servidor se reinicia en mitad de una
        partida, se recupera en vez de empezar de cero.
        """
        with self.candado:
            if self._partida is None or self._partida.estado == "terminada":
                fila = self.almacen.partida_abierta()
                if fila is not None:
                    self._partida = self._rehidratar(fila)
                else:
                    self._partida = self._nueva_partida()
            return self._partida

    def _nueva_partida(self) -> object:
        partida = self.mesa.sala.abrir_partida("10.00", patron="linea_h1")
        self._guardar(partida)
        return partida

    def _rehidratar(self, fila) -> object:
        """Reconstruye una partida guardada, con sus cartones y sus bolas."""
        from bingo.cartones import Bombo, Carton

        partida = self.mesa.sala.abrir_partida(
            fila["precio_carton"] / 100, patron=fila["patron"], id_=fila["id"]
        )
        partida.estado = fila["estado"]
        partida.ganador = fila["ganador"]
        partida.carton_ganador = fila["carton_ganador"]
        partida.premio = fila["premio"]
        partida.empezada = fila["empezada"]
        partida.terminada = fila["terminada"]
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
        self.almacen.guardar_partida({
            "id": partida.id, "patron": partida.patron, "precio_carton": partida.precio_carton,
            "estado": partida.estado, "bolas": ",".join(str(b) for b in partida.bombo.sacadas),
            "ganador": partida.ganador, "carton_ganador": partida.carton_ganador,
            "premio": partida.premio, "empezada": partida.empezada, "terminada": partida.terminada,
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
            "partidas": len(partidas),
            "apostado": apostado,
            "pagado": pagado,
            "margen": apostado - pagado,
        }


class Manejador(BaseHTTPRequestHandler):
    server_version = "BingoPiramide777/1.1"

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
        self.wfile.write(cuerpo)

    def _error(self, mensaje: str, codigo: int = 400) -> None:
        self._json({"error": mensaje}, codigo)

    def _leer_json(self) -> dict:
        largo = int(self.headers.get("Content-Length") or 0)
        if largo <= 0 or largo > 100_000:
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
        self.end_headers()
        self.wfile.write(cuerpo)

    def _retiro_json(self, r) -> dict:
        return {"id": r.id, "correo": r.correo, "centimos": r.centimos,
                "importe_texto": a_texto(r.centimos), "metodo": r.metodo,
                "detalles": r.detalles, "estado": r.estado, "pedido": r.pedido,
                "revisado": r.revisado, "revisado_por": r.revisado_por, "nota": r.nota}

    # -- GET --

    def do_GET(self) -> None:  # noqa: N802
        ruta = urlparse(self.path).path

        if ruta == "/api/salud":
            self._json({"estado": "bien", "servicio": "Bingo Pirámide 777"})
            return

        if ruta == "/api/partida":
            with self.juego.candado:
                self._json(self.juego.mesa.partida_publica(self.juego.partida().id))
            return

        if ruta == "/api/config":
            self._json({
                "retiro_minimo": self.juego.retiros.config.minimo,
                "retiro_minimo_texto": a_texto(self.juego.retiros.config.minimo),
                "retiro_tope_texto": a_texto(self.juego.retiros.config.tope_diario),
                "metodos": list(self.juego.retiros.config.metodos),
            })
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

        if ruta == "/api/admin/jugadores":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            with self.juego.candado:
                lista = [{"correo": u.correo, "nombre": u.nombre, "rol": u.rol,
                          "activo": u.activo, "creado": u.creado,
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

        if ruta == "/api/admin/retiros":
            if not self._admin():
                self._error("Solo para administración.", 403)
                return
            estado = None
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            if qs.get("estado"):
                estado = qs["estado"][0]
            with self.juego.candado:
                lista = [self._retiro_json(r) for r in self.juego.retiros.listar(estado=estado)]
            self._json({"retiros": lista})
            return

        if ruta == "/admin":
            self._estatico("admin.html")
            return

        self._estatico(ruta)

    # -- POST --

    def do_POST(self) -> None:  # noqa: N802
        ruta = urlparse(self.path).path
        datos = self._leer_json()

        if ruta == "/api/registro":
            try:
                with self.juego.candado:
                    self.juego.usuarios.registrar(datos.get("correo", ""), datos.get("clave", ""),
                                                  datos.get("nombre", ""))
                self._json({"ok": True, "mensaje": "Cuenta creada. Ya puedes entrar."})
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
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                centimos = a_centimos(datos.get("importe", ""))
                if centimos <= 0:
                    raise ErrorDeDinero("El importe tiene que ser mayor que cero.")
                with self.juego.candado:
                    self.juego.monedero.recargar(jugador, centimos, "recarga web")
                    saldo = self.juego.monedero.saldo(jugador)
                self._json({"ok": True, "saldo": saldo, "saldo_texto": a_texto(saldo)})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        if ruta == "/api/carton":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            try:
                with self.juego.candado:
                    partida = self.juego.partida()
                    carton_id, precio = self.juego.mesa.comprar_carton(partida.id, jugador)
                    carton = partida.cartones[carton_id]
                    self.juego.guardar_carton(partida, carton_id)
                    self.juego._guardar(partida)
                self._json({"ok": True, "carton": carton_id, "precio": precio,
                            "precio_texto": a_texto(precio), "numeros": carton.numeros,
                            "saldo": self.juego.monedero.saldo(jugador)})
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
                    partida = self.juego.partida()
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
                    partida = self.juego.partida()
                    res = self.juego.mesa.resolver_cantada(partida.id, jugador, datos.get("carton", ""))
                    partida.premio = res["premio"]
                    self.juego._guardar(partida)
                    res["premio_texto"] = a_texto(res["premio"])
                    res["saldo"] = self.juego.monedero.saldo(jugador)
                self._json({"ok": True, **res})
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

        if ruta == "/api/admin/usuario":
            admin = self._admin()
            if not admin:
                self._error("Solo para administración.", 403)
                return
            try:
                correo = (datos.get("correo") or "").strip().lower()
                if correo == admin:
                    raise ErrorDeRetiro("No puedes desactivar tu propia cuenta.")
                if "activo" in datos:
                    self.juego.usuarios.activar(correo, bool(datos["activo"]))
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
