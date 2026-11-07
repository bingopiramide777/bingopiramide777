"""Almacén de datos en SQLite. Todo lo que hay que conservar al reiniciar.

Un solo fichero, sin servidor que instalar. Cada operación de dinero va en una
transacción: o entra entera, o no entra. Nunca un saldo a medias.

Las conexiones de SQLite no se pueden compartir entre hilos sin cuidado, así que
hay un candado. El servidor es pequeño y no compite por el disco.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    correo  TEXT PRIMARY KEY,
    huella  TEXT NOT NULL,
    nombre  TEXT NOT NULL DEFAULT '',
    rol     TEXT NOT NULL DEFAULT 'jugador',
    activo  INTEGER NOT NULL DEFAULT 1,
    creado  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cuentas (
    correo   TEXT PRIMARY KEY,
    centimos INTEGER NOT NULL DEFAULT 0 CHECK (centimos >= 0)
);

CREATE TABLE IF NOT EXISTS movimientos (
    id            TEXT PRIMARY KEY,
    correo        TEXT NOT NULL,
    tipo          TEXT NOT NULL,
    centimos      INTEGER NOT NULL,
    saldo_despues INTEGER NOT NULL,
    motivo        TEXT NOT NULL DEFAULT '',
    cuando        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mov_correo ON movimientos(correo, cuando);

CREATE TABLE IF NOT EXISTS sesiones (
    token  TEXT PRIMARY KEY,
    correo TEXT NOT NULL,
    creada REAL NOT NULL,
    caduca REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS retiros (
    id          TEXT PRIMARY KEY,
    correo      TEXT NOT NULL,
    centimos    INTEGER NOT NULL,
    metodo      TEXT NOT NULL,
    detalles    TEXT NOT NULL DEFAULT '',
    estado      TEXT NOT NULL DEFAULT 'pendiente',
    pedido      REAL NOT NULL,
    revisado    REAL,
    revisado_por TEXT,
    nota        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_retiros_estado ON retiros(estado, pedido);

CREATE TABLE IF NOT EXISTS partidas (
    id             TEXT PRIMARY KEY,
    patron         TEXT NOT NULL,
    precio_carton  INTEGER NOT NULL,
    estado         TEXT NOT NULL,
    bolas          TEXT NOT NULL DEFAULT '',
    ganador        TEXT,
    carton_ganador TEXT,
    premio         INTEGER NOT NULL DEFAULT 0,
    empezada       REAL,
    terminada      REAL
);

CREATE TABLE IF NOT EXISTS depositos (
    id            TEXT PRIMARY KEY,
    correo        TEXT NOT NULL,
    centimos      INTEGER NOT NULL,
    metodo        TEXT NOT NULL,
    referencia    TEXT NOT NULL,
    banco         TEXT NOT NULL DEFAULT '',
    dia           TEXT NOT NULL,
    estado        TEXT NOT NULL DEFAULT 'pendiente',
    nota          TEXT NOT NULL DEFAULT '',
    pedido        REAL NOT NULL,
    revisado      REAL,
    revisado_por  TEXT
);
CREATE INDEX IF NOT EXISTS idx_depositos ON depositos(estado, pedido);
CREATE UNIQUE INDEX IF NOT EXISTS idx_depositos_ref
    ON depositos(referencia, dia) WHERE estado != 'rechazado';

CREATE TABLE IF NOT EXISTS glenis (
    id        TEXT PRIMARY KEY,
    quien     TEXT NOT NULL,
    texto     TEXT NOT NULL,
    acciones  TEXT NOT NULL DEFAULT '',
    cuando    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_glenis ON glenis(cuando);

CREATE TABLE IF NOT EXISTS codigos (
    id       TEXT PRIMARY KEY,
    correo   TEXT NOT NULL,
    huella   TEXT NOT NULL,
    intentos INTEGER NOT NULL DEFAULT 0,
    usado    INTEGER NOT NULL DEFAULT 0,
    creado   REAL NOT NULL,
    caduca   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_codigos_correo ON codigos(correo, usado, creado);

CREATE TABLE IF NOT EXISTS cartones (
    id       TEXT PRIMARY KEY,
    partida  TEXT NOT NULL,
    correo   TEXT NOT NULL,
    numeros  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cartones_partida ON cartones(partida);
"""


class Almacen:
    def __init__(self, ruta: str = ":memory:") -> None:
        self.ruta = ruta
        if ruta not in (":memory:", "") and os.path.dirname(ruta):
            os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        self._candado = threading.RLock()
        self._con = sqlite3.connect(ruta, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA foreign_keys=ON")
        self._con.executescript(ESQUEMA)
        self._con.commit()
        self._migrar()

    def _migrar(self) -> None:
        """Añade columnas a bases de datos creadas antes de que existieran.

        Sin esto, actualizar el programa rompería la base de datos de quien ya
        lo tenía funcionando, y perdería las cuentas.
        """
        columnas = {f["name"] for f in self._todos("PRAGMA table_info(usuarios)")}
        nuevas = (("pregunta", "TEXT NOT NULL DEFAULT ''"),
                  ("respuesta_huella", "TEXT NOT NULL DEFAULT ''"))
        for nombre, definicion in nuevas:
            if nombre not in columnas:
                with self.transaccion() as c:
                    c.execute(f"ALTER TABLE usuarios ADD COLUMN {nombre} {definicion}")

    @contextmanager
    def transaccion(self) -> Iterator[sqlite3.Connection]:
        """Todo o nada. Si algo falla dentro, se deshace entero."""
        with self._candado:
            try:
                yield self._con
                self._con.commit()
            except Exception:
                self._con.rollback()
                raise

    def cerrar(self) -> None:
        with self._candado:
            self._con.close()

    def _uno(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        with self._candado:
            return self._con.execute(sql, args).fetchone()

    def _todos(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._candado:
            return list(self._con.execute(sql, args).fetchall())

    # -- usuarios --

    def asegurar_cuenta(self, correo: str) -> None:
        """Crea la cuenta si no existe. Sin usuario detrás no se puede entrar,
        pero así un movimiento no falla por una cuenta que aún no se ha abierto."""
        with self.transaccion() as c:
            c.execute("INSERT OR IGNORE INTO cuentas (correo, centimos) VALUES (?, 0)", (correo,))

    def crear_usuario(self, correo: str, huella: str, nombre: str, rol: str, creado: float,
                      pregunta: str = "", respuesta_huella: str = "") -> None:
        with self.transaccion() as c:
            c.execute(
                "INSERT INTO usuarios (correo, huella, nombre, rol, creado, pregunta, respuesta_huella)"
                " VALUES (?,?,?,?,?,?,?)",
                (correo, huella, nombre, rol, creado, pregunta, respuesta_huella),
            )
            c.execute("INSERT INTO cuentas (correo, centimos) VALUES (?, 0)", (correo,))

    def guardar_pregunta(self, correo: str, pregunta: str, respuesta_huella: str) -> None:
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET pregunta = ?, respuesta_huella = ? WHERE correo = ?",
                      (pregunta, respuesta_huella, correo))

    def usuario(self, correo: str) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM usuarios WHERE correo = ?", (correo,))

    def usuarios(self) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM usuarios ORDER BY creado")

    def cambiar_huella(self, correo: str, huella: str) -> None:
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET huella = ? WHERE correo = ?", (huella, correo))

    def cambiar_rol(self, correo: str, rol: str) -> None:
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET rol = ? WHERE correo = ?", (rol, correo))

    def cambiar_activo(self, correo: str, activo: bool) -> None:
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET activo = ? WHERE correo = ?", (1 if activo else 0, correo))

    # -- dinero --

    def saldo(self, correo: str) -> int:
        fila = self._uno("SELECT centimos FROM cuentas WHERE correo = ?", (correo,))
        return int(fila["centimos"]) if fila else 0

    def aplicar_movimiento(
        self, correo: str, tipo: str, centimos: int, motivo: str, cuando: float, mov_id: str
    ) -> int:
        """Suma (o resta) al saldo y anota el movimiento. Devuelve el saldo nuevo.

        La comprobación de saldo negativo la hace la base de datos con un CHECK,
        y el UPDATE es condicional: dos peticiones a la vez no pueden dejar el
        saldo por debajo de cero.
        """
        with self.transaccion() as c:
            fila = c.execute("SELECT centimos FROM cuentas WHERE correo = ?", (correo,)).fetchone()
            if fila is None:
                raise KeyError(f"No hay cuenta para {correo!r}.")
            actual = int(fila["centimos"])
            nuevo = actual + centimos
            if nuevo < 0:
                raise ValueError(
                    f"Saldo insuficiente: hay {actual} céntimos y se intentan mover {centimos}."
                )
            c.execute("UPDATE cuentas SET centimos = ? WHERE correo = ?", (nuevo, correo))
            c.execute(
                "INSERT INTO movimientos (id, correo, tipo, centimos, saldo_despues, motivo, cuando)"
                " VALUES (?,?,?,?,?,?,?)",
                (mov_id, correo, tipo, centimos, nuevo, motivo, cuando),
            )
            return nuevo

    def movimientos(self, correo: str, limite: int = 200) -> list[sqlite3.Row]:
        return self._todos(
            "SELECT * FROM movimientos WHERE correo = ? ORDER BY cuando DESC LIMIT ?",
            (correo, limite),
        )

    def todos_los_movimientos(self, limite: int = 200) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM movimientos ORDER BY cuando DESC LIMIT ?", (limite,))

    def total_en_cuentas(self) -> int:
        fila = self._uno("SELECT COALESCE(SUM(centimos), 0) AS t FROM cuentas")
        return int(fila["t"]) if fila else 0

    # -- sesiones --

    def crear_sesion(self, token: str, correo: str, creada: float, caduca: float) -> None:
        with self.transaccion() as c:
            c.execute(
                "INSERT INTO sesiones (token, correo, creada, caduca) VALUES (?,?,?,?)",
                (token, correo, creada, caduca),
            )

    def sesion(self, token: str) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM sesiones WHERE token = ?", (token,))

    def borrar_sesion(self, token: str) -> None:
        with self.transaccion() as c:
            c.execute("DELETE FROM sesiones WHERE token = ?", (token,))

    def borrar_sesiones_de(self, correo: str) -> int:
        """Cierra todas las sesiones de una cuenta.

        Se usa al cambiar la contraseña: si alguien te había robado la cuenta,
        con esto se queda fuera aunque tú cambies la clave.
        """
        with self.transaccion() as c:
            cur = c.execute("DELETE FROM sesiones WHERE correo = ?", (correo,))
            return cur.rowcount

    def limpiar_sesiones_caducadas(self, ahora: float) -> int:
        with self.transaccion() as c:
            cur = c.execute("DELETE FROM sesiones WHERE caduca < ?", (ahora,))
            return cur.rowcount

    # -- retiros --

    def crear_retiro(self, datos: dict) -> None:
        with self.transaccion() as c:
            c.execute(
                "INSERT INTO retiros (id, correo, centimos, metodo, detalles, estado, pedido)"
                " VALUES (?,?,?,?,?,?,?)",
                (datos["id"], datos["correo"], datos["centimos"], datos["metodo"],
                 datos["detalles"], "pendiente", datos["pedido"]),
            )

    def retiro(self, id_: str) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM retiros WHERE id = ?", (id_,))

    def retiros(self, estado: str | None = None, correo: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM retiros WHERE 1=1"
        args: list = []
        if estado:
            sql += " AND estado = ?"
            args.append(estado)
        if correo:
            sql += " AND correo = ?"
            args.append(correo)
        sql += " ORDER BY pedido DESC"
        return self._todos(sql, tuple(args))

    def resolver_retiro(self, id_: str, estado: str, revisado: float, por: str, nota: str = "") -> int:
        """Cambia el estado de un retiro SOLO si sigue pendiente.

        Devuelve cuántas filas cambiaron: si es 0, alguien se adelantó y no hay
        que mover dinero otra vez.
        """
        with self.transaccion() as c:
            cur = c.execute(
                "UPDATE retiros SET estado = ?, revisado = ?, revisado_por = ?, nota = ?"
                " WHERE id = ? AND estado = 'pendiente'",
                (estado, revisado, por, nota, id_),
            )
            return cur.rowcount

    def retirado_pendiente(self, correo: str) -> int:
        fila = self._uno(
            "SELECT COALESCE(SUM(centimos), 0) AS t FROM retiros WHERE correo = ? AND estado = 'pendiente'",
            (correo,),
        )
        return int(fila["t"]) if fila else 0

    def retirado_hoy(self, correo: str, desde: float) -> int:
        fila = self._uno(
            "SELECT COALESCE(SUM(centimos), 0) AS t FROM retiros"
            " WHERE correo = ? AND pedido >= ? AND estado != 'rechazado'",
            (correo, desde),
        )
        return int(fila["t"]) if fila else 0

    # -- códigos de recuperación --

    def guardar_codigo(self, id_: str, correo: str, huella: str, creado: float, caduca: float) -> None:
        with self.transaccion() as c:
            # Un código nuevo anula los anteriores: solo vale el último.
            c.execute("UPDATE codigos SET usado = 1 WHERE correo = ? AND usado = 0", (correo,))
            c.execute("INSERT INTO codigos (id, correo, huella, creado, caduca) VALUES (?,?,?,?,?)",
                      (id_, correo, huella, creado, caduca))

    def codigo_pendiente(self, correo: str) -> sqlite3.Row | None:
        return self._uno(
            "SELECT * FROM codigos WHERE correo = ? AND usado = 0 ORDER BY creado DESC LIMIT 1",
            (correo,),
        )

    def codigos_recientes(self, correo: str, desde: float) -> int:
        fila = self._uno("SELECT COUNT(*) AS n FROM codigos WHERE correo = ? AND creado >= ?",
                         (correo, desde))
        return int(fila["n"]) if fila else 0

    def usar_codigo(self, id_: str) -> None:
        with self.transaccion() as c:
            c.execute("UPDATE codigos SET usado = 1 WHERE id = ?", (id_,))

    def fallar_codigo(self, id_: str) -> int:
        """Suma un intento fallido y devuelve el total. Si se pasa, se anula."""
        with self.transaccion() as c:
            c.execute("UPDATE codigos SET intentos = intentos + 1 WHERE id = ?", (id_,))
            fila = c.execute("SELECT intentos FROM codigos WHERE id = ?", (id_,)).fetchone()
            intentos = int(fila["intentos"]) if fila else 0
            if intentos >= 5:
                c.execute("UPDATE codigos SET usado = 1 WHERE id = ?", (id_,))
            return intentos

    # -- depósitos --

    def crear_deposito(self, d: dict) -> None:
        with self.transaccion() as c:
            c.execute(
                "INSERT INTO depositos (id, correo, centimos, metodo, referencia, banco, dia,"
                " estado, nota, pedido) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (d["id"], d["correo"], d["centimos"], d["metodo"], d["referencia"],
                 d.get("banco", ""), d["dia"], "pendiente", d.get("nota", ""), d["pedido"]),
            )

    def deposito(self, id_: str) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM depositos WHERE id = ?", (id_,))

    def depositos(self, estado: str | None = None, correo: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM depositos WHERE 1=1"
        args: list = []
        if estado:
            sql += " AND estado = ?"
            args.append(estado)
        if correo:
            sql += " AND correo = ?"
            args.append(correo)
        sql += " ORDER BY pedido DESC"
        return self._todos(sql, tuple(args))

    def referencia_usada(self, referencia: str, dia: str) -> sqlite3.Row | None:
        """Busca si esa referencia ya se usó ese día.

        Es el freno contra el mismo pago reclamado dos veces, o contra una captura
        de pantalla reenviada.
        """
        return self._uno(
            "SELECT * FROM depositos WHERE referencia = ? AND dia = ? AND estado != 'rechazado'",
            (referencia, dia),
        )

    def resolver_deposito(self, id_: str, estado: str, revisado: float, por: str,
                          nota: str = "") -> int:
        with self.transaccion() as c:
            cur = c.execute(
                "UPDATE depositos SET estado = ?, revisado = ?, revisado_por = ?, nota = ?"
                " WHERE id = ? AND estado = 'pendiente'",
                (estado, revisado, por, nota, id_),
            )
            return cur.rowcount

    def deposito_hoy(self, correo: str, desde: float) -> int:
        """Cuánto ha declarado ese jugador hoy, sumando pendientes y acreditados.

        Cuentan los pendientes a propósito: si solo contaran los acreditados, se
        podrían declarar mil depósitos sin revisar y saltarse el tope.
        """
        fila = self._uno(
            "SELECT COALESCE(SUM(centimos), 0) AS t FROM depositos"
            " WHERE correo = ? AND pedido >= ? AND estado IN ('pendiente', 'acreditado')",
            (correo, desde),
        )
        return int(fila["t"]) if fila else 0

    # -- registro de Glenis IA --

    def anotar_glenis(self, id_: str, quien: str, texto: str, acciones: str, cuando: float) -> None:
        with self.transaccion() as c:
            c.execute("INSERT INTO glenis (id, quien, texto, acciones, cuando) VALUES (?,?,?,?,?)",
                      (id_, quien, texto, acciones, cuando))

    def historial_glenis(self, limite: int = 40) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM glenis ORDER BY cuando DESC LIMIT ?", (limite,))

    # -- partidas --

    def guardar_partida(self, p: dict) -> None:
        with self.transaccion() as c:
            c.execute(
                "INSERT INTO partidas (id, patron, precio_carton, estado, bolas, ganador,"
                " carton_ganador, premio, empezada, terminada)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET patron=excluded.patron,"
                " precio_carton=excluded.precio_carton, estado=excluded.estado, bolas=excluded.bolas,"
                " ganador=excluded.ganador, carton_ganador=excluded.carton_ganador,"
                " premio=excluded.premio, empezada=excluded.empezada, terminada=excluded.terminada",
                (p["id"], p["patron"], p["precio_carton"], p["estado"], p.get("bolas", ""),
                 p.get("ganador"), p.get("carton_ganador"), p.get("premio", 0),
                 p.get("empezada"), p.get("terminada")),
            )

    def partida(self, id_: str) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM partidas WHERE id = ?", (id_,))

    def partida_abierta(self) -> sqlite3.Row | None:
        return self._uno(
            "SELECT * FROM partidas WHERE estado != 'terminada' ORDER BY rowid DESC LIMIT 1"
        )

    def partidas(self, limite: int = 100) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM partidas ORDER BY rowid DESC LIMIT ?", (limite,))

    def guardar_carton(self, id_: str, partida: str, correo: str, numeros: str) -> None:
        with self.transaccion() as c:
            c.execute(
                "INSERT INTO cartones (id, partida, correo, numeros) VALUES (?,?,?,?)",
                (id_, partida, correo, numeros),
            )

    def cartones(self, partida: str) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM cartones WHERE partida = ?", (partida,))
