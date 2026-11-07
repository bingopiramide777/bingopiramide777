"""Servidor web de Bingo Pirámide 777.

Solo biblioteca estándar: http.server. Sin dependencias que instalar ni que
actualizar. Sirve la interfaz y una API pequeña para el bingo.
"""

from __future__ import annotations

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from bingo import MesaBingo, Sala
from nucleo import ErrorDeDinero, ErrorDeMonedero, Monedero, a_centimos, a_texto
from nucleo.usuarios import ErrorDeUsuario, Usuarios

RAIZ_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class Juego:
    """Estado de la aplicación: usuarios, monedero y mesas de bingo.

    Un único candado protege el dinero. Es un servidor pequeño y así el saldo
    nunca se descuadra por dos peticiones a la vez.
    """

    def __init__(self) -> None:
        self.candado = threading.RLock()
        self.usuarios = Usuarios()
        self.monedero = Monedero()
        self.mesa = MesaBingo(sala=Sala(), monedero=self.monedero)
        self._partida = None

    def partida(self):
        """Devuelve la partida abierta, abriendo una nueva si no hay."""
        with self.candado:
            if self._partida is None or self._partida.estado == "terminada":
                self._partida = self.mesa.sala.abrir_partida("10.00", patron="linea_h1")
            return self._partida


class Manejador(BaseHTTPRequestHandler):
    server_version = "BingoPiramide777/1.0"

    @property
    def juego(self) -> Juego:
        return self.server.juego

    # -- utilidades --

    def _json(self, datos: dict, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
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
        if cabecera.startswith("Bearer "):
            return cabecera[7:].strip()
        return ""

    def _jugador(self) -> str | None:
        sesion = self.juego.usuarios.sesion(self._token())
        return sesion.correo if sesion else None

    def _estatico(self, ruta: str) -> None:
        # Solo se sirven ficheros de static/, y nunca con ".." para no salir de ahí.
        nombre = "index.html" if ruta in ("/", "") else ruta.lstrip("/")
        if ".." in nombre or nombre.startswith("/"):
            self._error("Ruta no válida.", 400)
            return
        camino = os.path.join(RAIZ_WEB, nombre)
        if not os.path.isfile(camino):
            self._error("No encontrado.", 404)
            return
        tipos = {".html": "text/html", ".css": "text/css", ".js": "text/javascript",
                 ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}
        ext = os.path.splitext(camino)[1]
        with open(camino, "rb") as f:
            cuerpo = f.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{tipos.get(ext, 'application/octet-stream')}; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(cuerpo)

    # -- rutas --

    def do_GET(self) -> None:  # noqa: N802
        ruta = urlparse(self.path).path
        if ruta == "/api/salud":
            self._json({"estado": "bien", "servicio": "Bingo Pirámide 777"})
            return
        if ruta == "/api/partida":
            with self.juego.candado:
                self._json(self.juego.mesa.partida_publica(self.juego.partida().id))
            return
        if ruta == "/api/saldo":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                self._json({"saldo": self.juego.monedero.saldo(jugador),
                            "saldo_texto": a_texto(self.juego.monedero.saldo(jugador))})
            return
        if ruta == "/api/historial":
            jugador = self._jugador()
            if not jugador:
                self._error("Hace falta entrar.", 401)
                return
            with self.juego.candado:
                movs = [{"tipo": m.tipo, "centimos": m.centimos, "motivo": m.motivo,
                         "saldo": m.saldo_despues, "cuando": m.cuando}
                        for m in self.juego.monedero.historial(jugador)]
            self._json({"movimientos": movs})
            return
        self._estatico(ruta)

    def do_POST(self) -> None:  # noqa: N802
        ruta = urlparse(self.path).path
        datos = self._leer_json()

        if ruta == "/api/registro":
            try:
                with self.juego.candado:
                    self.juego.usuarios.registrar(datos.get("correo", ""), datos.get("clave", ""),
                                             datos.get("nombre", ""))
                self._json({"ok": True, "mensaje": "Cuenta creada. Ya puedes entrar."})
            except ErrorDeUsuario as exc:
                self._error(str(exc))
            return

        if ruta == "/api/entrar":
            try:
                with self.juego.candado:
                    sesion = self.juego.usuarios.entrar(datos.get("correo", ""), datos.get("clave", ""))
                self._json({"ok": True, "token": sesion.token,
                            "caduca": sesion.caduca, "correo": sesion.correo})
            except ErrorDeUsuario as exc:
                self._error(str(exc), 401)
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
            except (ErrorDeDinero, ErrorDeMonedero) as exc:
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
                self._json({
                    "ok": True,
                    "carton": carton_id,
                    "precio": precio,
                    "precio_texto": a_texto(precio),
                    "numeros": carton.numeros,
                    "saldo": self.juego.monedero.saldo(jugador),
                })
            except Exception as exc:  # noqa: BLE001 - se traduce a un error legible
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
                    res["premio_texto"] = a_texto(res["premio"])
                    res["saldo"] = self.juego.monedero.saldo(jugador)
                self._json({"ok": True, **res})
            except Exception as exc:  # noqa: BLE001
                self._error(str(exc))
            return

        self._error("Ruta no encontrada.", 404)

    def log_message(self, formato: str, *args) -> None:
        # Silencio en consola salvo errores, para no ensuciar los registros.
        if not re.match(r'.*"(GET|POST) /(api/)?(salud|partida|saldo)"', formato % args):
            super().log_message(formato, *args)


def crear_servidor(host: str = "0.0.0.0", puerto: int = 8000, juego: Juego | None = None) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer((host, puerto), Manejador)
    servidor.juego = juego or Juego()
    return servidor


def main() -> None:
    puerto = int(os.environ.get("PORT", "8000"))
    servidor = crear_servidor(puerto=puerto)
    print(f"Bingo Pirámide 777 escuchando en http://0.0.0.0:{puerto}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando…")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
