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
import time
from contextlib import contextmanager
from typing import Iterator

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    correo  TEXT PRIMARY KEY,
    huella  TEXT NOT NULL,
    nombre  TEXT NOT NULL DEFAULT '',
    rol     TEXT NOT NULL DEFAULT 'jugador',
    activo  INTEGER NOT NULL DEFAULT 1,
    creado  REAL NOT NULL,
    comision_pct INTEGER NOT NULL DEFAULT -1,
    verificado INTEGER NOT NULL DEFAULT 1,
    datos_cobro TEXT NOT NULL DEFAULT '',
    codigo_amigo TEXT NOT NULL DEFAULT '',
    referido_por TEXT NOT NULL DEFAULT '',
    codigo_invitacion TEXT NOT NULL DEFAULT '',
    invitado_por TEXT NOT NULL DEFAULT '',
    foto TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_codigo ON usuarios(codigo_amigo)
    WHERE codigo_amigo <> '';

CREATE TABLE IF NOT EXISTS referidos (
    id       TEXT PRIMARY KEY,
    partida  TEXT NOT NULL,
    referido TEXT NOT NULL,
    padrino  TEXT NOT NULL,
    centimos INTEGER NOT NULL,
    cuando   REAL NOT NULL,
    UNIQUE(partida, padrino)
);
CREATE INDEX IF NOT EXISTS idx_referidos_padrino ON referidos(padrino, cuando);

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
    sala           TEXT NOT NULL DEFAULT '',
    patron         TEXT NOT NULL,
    precio_carton  INTEGER NOT NULL,
    estado         TEXT NOT NULL,
    bolas          TEXT NOT NULL DEFAULT '',
    ganador        TEXT,
    carton_ganador TEXT,
    premio         INTEGER NOT NULL DEFAULT 0,
    empezada       REAL,
    terminada      REAL,
    ganadores      TEXT NOT NULL DEFAULT '',
    plazas         INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_partidas_terminada ON partidas(estado, terminada);

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
    revisado_por  TEXT,
    pais          TEXT NOT NULL DEFAULT 'VE',
    comision      INTEGER NOT NULL DEFAULT 0,
    acreditado    INTEGER NOT NULL DEFAULT 0
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
    caduca   REAL NOT NULL,
    tipo     TEXT NOT NULL DEFAULT 'recuperacion'
);
CREATE INDEX IF NOT EXISTS idx_codigos_correo ON codigos(correo, usado, creado);

CREATE TABLE IF NOT EXISTS salas (
    id             TEXT PRIMARY KEY,
    nombre         TEXT NOT NULL,
    modo           TEXT NOT NULL,
    precio_carton  INTEGER NOT NULL,
    dueno          TEXT NOT NULL DEFAULT '',
    publica        INTEGER NOT NULL DEFAULT 1,
    activa         INTEGER NOT NULL DEFAULT 1,
    creada         REAL NOT NULL,
    es_evento      INTEGER NOT NULL DEFAULT 0,
    aforo          INTEGER NOT NULL DEFAULT 0,
    premios_pct    TEXT NOT NULL DEFAULT '',
    tipo_juego     TEXT NOT NULL DEFAULT '',
    cupo_cartones  INTEGER NOT NULL DEFAULT 0,
    max_cartones   INTEGER NOT NULL DEFAULT 0,
    fecha_partida  TEXT NOT NULL DEFAULT '',
    hora_partida   TEXT NOT NULL DEFAULT '',
    pais           TEXT NOT NULL DEFAULT 'VE',
    es_trabajo     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_salas_dueno ON salas(dueno);

CREATE TABLE IF NOT EXISTS cartones (
    id       TEXT PRIMARY KEY,
    partida  TEXT NOT NULL,
    correo   TEXT NOT NULL,
    numeros  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cartones_partida ON cartones(partida);

CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS billeteras (
    correo    TEXT PRIMARY KEY,
    red       TEXT NOT NULL,
    direccion TEXT NOT NULL,
    creada    REAL NOT NULL
);
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
                  ("respuesta_huella", "TEXT NOT NULL DEFAULT ''"),
                  ("comision_pct", "INTEGER NOT NULL DEFAULT -1"),
                  ("verificado", "INTEGER NOT NULL DEFAULT 1"),
                  ("datos_cobro", "TEXT NOT NULL DEFAULT ''"),
                  ("codigo_amigo", "TEXT NOT NULL DEFAULT ''"),
                  ("referido_por", "TEXT NOT NULL DEFAULT ''"),
                  ("codigo_invitacion", "TEXT NOT NULL DEFAULT ''"),
                  ("invitado_por", "TEXT NOT NULL DEFAULT ''"),
                  ("foto", "TEXT NOT NULL DEFAULT ''"))
        for nombre, definicion in nuevas:
            if nombre not in columnas:
                with self.transaccion() as c:
                    c.execute(f"ALTER TABLE usuarios ADD COLUMN {nombre} {definicion}")
        # El código de invitación (el de la sala de trabajo, aparte del de
        # referidos) nació después: el índice se crea aquí, con la columna ya puesta.
        with self.transaccion() as c:
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_invitacion"
                      " ON usuarios(codigo_invitacion) WHERE codigo_invitacion <> ''")

        # La partida aprendió a decir a qué sala pertenece.
        columnas_p = {f["name"] for f in self._todos("PRAGMA table_info(partidas)")}
        if "sala" not in columnas_p:
            with self.transaccion() as c:
                c.execute("ALTER TABLE partidas ADD COLUMN sala TEXT NOT NULL DEFAULT ''")
        # Y a llevar varios ganadores (la sala de eventos reparte 1º, 2º y 3º).
        nuevas_p = (("ganadores", "TEXT NOT NULL DEFAULT ''"),
                    ("plazas", "INTEGER NOT NULL DEFAULT 1"))
        for nombre, definicion in nuevas_p:
            if nombre not in columnas_p:
                with self.transaccion() as c:
                    c.execute(f"ALTER TABLE partidas ADD COLUMN {nombre} {definicion}")

        # Las salas aprendieron a ser de evento, con aforo y premios por porcentaje.
        columnas_s = {f["name"] for f in self._todos("PRAGMA table_info(salas)")}
        nuevas_s = (("es_evento", "INTEGER NOT NULL DEFAULT 0"),
                    ("aforo", "INTEGER NOT NULL DEFAULT 0"),
                    ("premios_pct", "TEXT NOT NULL DEFAULT ''"),
                    ("tipo_juego", "TEXT NOT NULL DEFAULT ''"),
                    ("cupo_cartones", "INTEGER NOT NULL DEFAULT 0"),
                    ("max_cartones", "INTEGER NOT NULL DEFAULT 0"),
                    ("fecha_partida", "TEXT NOT NULL DEFAULT ''"),
                    ("es_trabajo", "INTEGER NOT NULL DEFAULT 0"))
        for nombre, definicion in nuevas_s:
            if nombre not in columnas_s:
                with self.transaccion() as c:
                    c.execute(f"ALTER TABLE salas ADD COLUMN {nombre} {definicion}")

        # Cada sala nació sin país. Las que ya existen son de la casa, así que se
        # marcan Venezuela (el país por defecto).
        columnas_s2 = {f["name"] for f in self._todos("PRAGMA table_info(salas)")}
        if "pais" not in columnas_s2:
            with self.transaccion() as c:
                c.execute("ALTER TABLE salas ADD COLUMN pais TEXT NOT NULL DEFAULT 'VE'")
        # La sala aprendió a guardar la hora aparte del día.
        if "hora_partida" not in columnas_s2:
            with self.transaccion() as c:
                c.execute("ALTER TABLE salas ADD COLUMN hora_partida TEXT NOT NULL DEFAULT ''")

        # Los códigos aprendieron a distinguir para qué son (recuperar o verificar).
        columnas_c = {f["name"] for f in self._todos("PRAGMA table_info(codigos)")}
        if "tipo" not in columnas_c:
            with self.transaccion() as c:
                c.execute("ALTER TABLE codigos ADD COLUMN tipo TEXT NOT NULL DEFAULT 'recuperacion'")

        # Los depósitos aprendieron a guardar de qué país viene el jugador.
        columnas_d = {f["name"] for f in self._todos("PRAGMA table_info(depositos)")}
        if "pais" not in columnas_d:
            with self.transaccion() as c:
                c.execute("ALTER TABLE depositos ADD COLUMN pais TEXT NOT NULL DEFAULT 'VE'")
        # Y a guardar la comisión de la app y lo que de verdad se abonó.
        nuevas_d = (("comision", "INTEGER NOT NULL DEFAULT 0"),
                    ("acreditado", "INTEGER NOT NULL DEFAULT 0"))
        for nombre, definicion in nuevas_d:
            if nombre not in columnas_d:
                with self.transaccion() as c:
                    c.execute(f"ALTER TABLE depositos ADD COLUMN {nombre} {definicion}")

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
                      pregunta: str = "", respuesta_huella: str = "",
                      verificado: bool = True, codigo_amigo: str = "",
                      referido_por: str = "") -> None:
        with self.transaccion() as c:
            c.execute(
                "INSERT INTO usuarios (correo, huella, nombre, rol, creado, pregunta,"
                " respuesta_huella, verificado, codigo_amigo, referido_por)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (correo, huella, nombre, rol, creado, pregunta, respuesta_huella,
                 1 if verificado else 0, codigo_amigo, referido_por),
            )
            c.execute("INSERT INTO cuentas (correo, centimos) VALUES (?, 0)", (correo,))

    def usuario_por_codigo(self, codigo: str) -> sqlite3.Row | None:
        """El dueño de un código de amigo (vacío si nadie lo tiene)."""
        codigo = (codigo or "").strip().upper()
        if not codigo:
            return None
        return self._uno("SELECT * FROM usuarios WHERE codigo_amigo = ?", (codigo,))

    def usuario_por_invitacion(self, codigo: str) -> sqlite3.Row | None:
        """El dueño de un código de invitación a la sala de trabajo."""
        codigo = (codigo or "").strip().upper()
        if not codigo:
            return None
        return self._uno("SELECT * FROM usuarios WHERE codigo_invitacion = ?", (codigo,))

    def referidos_de(self, padrino: str, limite: int = 200) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM referidos WHERE padrino = ? ORDER BY cuando DESC LIMIT ?",
                           (padrino, limite))

    def referidos(self, limite: int = 500) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM referidos ORDER BY cuando DESC LIMIT ?", (limite,))

    def anotar_referido(self, id_: str, partida: str, referido: str, padrino: str,
                        centimos: int, cuando: float) -> bool:
        """Apunta la comisión de un referido. Devuelve False si ya estaba anotada.

        La clave (partida, referido) hace que reintentar no pague dos veces.
        """
        with self.transaccion() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO referidos (id, partida, referido, padrino, centimos,"
                " cuando) VALUES (?,?,?,?,?,?)",
                (id_, partida, referido, padrino, centimos, cuando),
            )
            return cur.rowcount > 0

    def total_referidos(self, padrino: str) -> int:
        fila = self._uno("SELECT COALESCE(SUM(centimos), 0) AS t FROM referidos WHERE padrino = ?",
                         (padrino,))
        return int(fila["t"]) if fila else 0

    def pagado_en_partida(self, partida: str) -> int:
        """Cuánto se ha pagado ya a padrinos por esta partida (para no pasarse)."""
        fila = self._uno("SELECT COALESCE(SUM(centimos), 0) AS t FROM referidos WHERE partida = ?",
                         (partida,))
        return int(fila["t"]) if fila else 0

    def invitados_de(self, padrino: str) -> list[sqlite3.Row]:
        return self._todos("SELECT correo, nombre, creado FROM usuarios WHERE referido_por = ?"
                           " ORDER BY creado", (padrino,))

    def invitados_de_invitacion(self, quien: str) -> list[str]:
        """Los correos que entraron a la sala de trabajo con el código de `quien`.

        Va por la columna `invitado_por`, que es del código de invitación (sala de
        trabajo), no del de amigo: así los referidos y la captación no se mezclan.
        """
        return [f["correo"] for f in self._todos(
            "SELECT correo FROM usuarios WHERE invitado_por = ? ORDER BY creado", (quien,))]

    def guardar_pregunta(self, correo: str, pregunta: str, respuesta_huella: str) -> None:
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET pregunta = ?, respuesta_huella = ? WHERE correo = ?",
                      (pregunta, respuesta_huella, correo))

    def usuario(self, correo: str) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM usuarios WHERE correo = ?", (correo,))

    def fijar_codigo_amigo(self, correo: str, codigo: str) -> None:
        """Asigna el código de amigo de una cuenta que aún no lo tenía."""
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET codigo_amigo = ? WHERE correo = ?", (codigo, correo))

    def fijar_codigo_invitacion(self, correo: str, codigo: str,
                                invitado_por: str = "") -> None:
        """Asigna el código de invitación a la sala de trabajo de una cuenta.

        Es un código aparte del de amigo: sirve para invitar a la sala de trabajo
        (captación de gente nueva), no para el sistema de referidos. `invitado_por`
        es quién lo trajo, solo para saber de quién es la gente.
        """
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET codigo_invitacion = ?, invitado_por = ?"
                      " WHERE correo = ?", (codigo, invitado_por, correo))

    def cambiar_foto(self, correo: str, foto: str) -> None:
        """Guarda la foto de perfil (vacío = quitarla)."""
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET foto = ? WHERE correo = ?", (foto or "", correo))

    def foto_de(self, correo: str) -> str:
        fila = self._uno("SELECT foto FROM usuarios WHERE correo = ?", (correo,))
        return (fila["foto"] if fila else "") or ""

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

    def cambiar_comision(self, correo: str, pct: int) -> None:
        """Fija el % de comisión de anfitrión de una cuenta (-1 = usar el de siempre)."""
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET comision_pct = ? WHERE correo = ?", (int(pct), correo))

    def guardar_datos_cobro(self, correo: str, paquete: str) -> None:
        """Guarda la ficha de cobro CIFRADA. El almacén no sabe descifrarla."""
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET datos_cobro = ? WHERE correo = ?", (paquete, correo))

    def marcar_verificado(self, correo: str, verificado: bool = True) -> None:
        with self.transaccion() as c:
            c.execute("UPDATE usuarios SET verificado = ? WHERE correo = ?",
                      (1 if verificado else 0, correo))

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

    def movimientos_por_motivo(self, fragmento: str) -> list[sqlite3.Row]:
        """Movimientos cuyo motivo contiene un texto (p. ej. 'comisión de sala').

        Sirve para auditar que un cobro no se haya hecho dos veces.
        """
        return self._todos(
            "SELECT * FROM movimientos WHERE motivo LIKE ? ORDER BY cuando",
            (f"%{fragmento}%",))

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

    def guardar_codigo(self, id_: str, correo: str, huella: str, creado: float, caduca: float,
                       tipo: str = "recuperacion") -> None:
        with self.transaccion() as c:
            # Un código nuevo anula los anteriores del mismo tipo: solo vale el último.
            c.execute("UPDATE codigos SET usado = 1 WHERE correo = ? AND usado = 0 AND tipo = ?",
                      (correo, tipo))
            c.execute("INSERT INTO codigos (id, correo, huella, creado, caduca, tipo)"
                      " VALUES (?,?,?,?,?,?)", (id_, correo, huella, creado, caduca, tipo))

    def codigo_pendiente(self, correo: str, tipo: str = "recuperacion") -> sqlite3.Row | None:
        return self._uno(
            "SELECT * FROM codigos WHERE correo = ? AND usado = 0 AND tipo = ?"
            " ORDER BY creado DESC LIMIT 1", (correo, tipo),
        )

    def codigos_recientes(self, correo: str, desde: float,
                          tipo: str | None = None) -> int:
        if tipo is None:
            fila = self._uno("SELECT COUNT(*) AS n FROM codigos WHERE correo = ? AND creado >= ?",
                             (correo, desde))
        else:
            fila = self._uno(
                "SELECT COUNT(*) AS n FROM codigos WHERE correo = ? AND creado >= ? AND tipo = ?",
                (correo, desde, tipo))
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
                " estado, nota, pedido, pais) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (d["id"], d["correo"], d["centimos"], d["metodo"], d["referencia"],
                 d.get("banco", ""), d["dia"], "pendiente", d.get("nota", ""), d["pedido"],
                 d.get("pais", "VE")),
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
                          nota: str = "", comision: int = 0, acreditado: int = 0) -> int:
        with self.transaccion() as c:
            cur = c.execute(
                "UPDATE depositos SET estado = ?, revisado = ?, revisado_por = ?, nota = ?,"
                " comision = ?, acreditado = ?"
                " WHERE id = ? AND estado = 'pendiente'",
                (estado, revisado, por, nota, comision, acreditado, id_),
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
                "INSERT INTO partidas (id, sala, patron, precio_carton, estado, bolas, ganador,"
                " carton_ganador, premio, empezada, terminada, ganadores, plazas)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET sala=excluded.sala, patron=excluded.patron,"
                " precio_carton=excluded.precio_carton, estado=excluded.estado, bolas=excluded.bolas,"
                " ganador=excluded.ganador, carton_ganador=excluded.carton_ganador,"
                " premio=excluded.premio, empezada=excluded.empezada, terminada=excluded.terminada,"
                " ganadores=excluded.ganadores, plazas=excluded.plazas",
                (p["id"], p.get("sala", ""), p["patron"], p["precio_carton"], p["estado"],
                 p.get("bolas", ""), p.get("ganador"), p.get("carton_ganador"),
                 p.get("premio", 0), p.get("empezada"), p.get("terminada"),
                 p.get("ganadores", ""), p.get("plazas", 1)),
            )

    def partida(self, id_: str) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM partidas WHERE id = ?", (id_,))

    def borrar_partida(self, id_: str) -> None:
        """Elimina una partida sin terminar que todavía no ha vendido cartones.

        Se usa cuando la administración cambia los puestos o el precio de la sala
        de eventos antes de que empiece: la partida vieja se tira para que la
        siguiente nazca con los datos nuevos.
        """
        with self.transaccion() as c:
            c.execute("DELETE FROM partidas WHERE id = ?", (id_,))

    def partida_abierta(self) -> sqlite3.Row | None:
        return self._uno(
            "SELECT * FROM partidas WHERE estado != 'terminada' ORDER BY rowid DESC LIMIT 1"
        )

    def partida_abierta_de(self, sala: str) -> sqlite3.Row | None:
        """La partida sin terminar de una sala concreta."""
        return self._uno(
            "SELECT * FROM partidas WHERE estado != 'terminada' AND sala = ?"
            " ORDER BY rowid DESC LIMIT 1", (sala,))

    def partidas(self, limite: int = 100, sala: str | None = None) -> list[sqlite3.Row]:
        if sala is None:
            return self._todos("SELECT * FROM partidas ORDER BY rowid DESC LIMIT ?", (limite,))
        return self._todos(
            "SELECT * FROM partidas WHERE sala = ? ORDER BY rowid DESC LIMIT ?", (sala, limite))

    def ganadores_recientes(self, limite: int = 12) -> list[dict]:
        """Los últimos que cantaron bingo, para el escaparate de la portada.

        Se junta la partida terminada con su sala (para el nombre) y con el
        jugador (para mostrar solo el nombre, nunca el correo entero). La lista
        va de lo más reciente a lo más viejo.
        """
        filas = self._todos(
            "SELECT p.terminada, p.premio, p.ganador, p.sala,"
            " s.nombre AS sala_nombre, u.nombre AS jugador_nombre"
            " FROM partidas p"
            " LEFT JOIN salas s ON s.id = p.sala"
            " LEFT JOIN usuarios u ON u.correo = p.ganador"
            " WHERE p.estado = 'terminada' AND p.ganador IS NOT NULL AND p.ganador != ''"
            " ORDER BY p.terminada DESC LIMIT ?", (limite,))
        return [{"cuando": f["terminada"], "premio": f["premio"] or 0,
                 "sala": f["sala_nombre"] or f["sala"] or "",
                 "nombre": self._nombre_publico(f["jugador_nombre"], f["ganador"])}
                for f in filas]

    @staticmethod
    def _nombre_publico(nombre: str | None, correo: str | None) -> str:
        """Nombre a mostrar sin destapar el correo: 'Ana P.' o la parte de antes
        de la arroba con la inicial del apellido si el nombre viene vacío."""
        limpio = (nombre or "").strip()
        if limpio:
            partes = limpio.split()
            return partes[0] + (" " + partes[1][0] + "." if len(partes) > 1 else "")
        antes = (correo or "").split("@")[0].replace(".", " ").replace("_", " ").strip()
        return antes.title() if antes else "Jugador"

    # -- salas --

    def guardar_sala(self, s: dict) -> None:
        with self.transaccion() as c:
            c.execute(
                "INSERT INTO salas (id, nombre, modo, precio_carton, dueno, publica, activa,"
                " creada, es_evento, aforo, premios_pct, tipo_juego, cupo_cartones,"
                " max_cartones, fecha_partida, hora_partida, pais, es_trabajo)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, modo=excluded.modo,"
                " precio_carton=excluded.precio_carton, publica=excluded.publica,"
                " activa=excluded.activa, es_evento=excluded.es_evento, aforo=excluded.aforo,"
                " premios_pct=excluded.premios_pct, tipo_juego=excluded.tipo_juego,"
                " cupo_cartones=excluded.cupo_cartones, max_cartones=excluded.max_cartones,"
                " fecha_partida=excluded.fecha_partida, hora_partida=excluded.hora_partida,"
                " pais=excluded.pais,"
                " es_trabajo=excluded.es_trabajo",
                (s["id"], s["nombre"], s["modo"], s["precio_carton"], s.get("dueno", ""),
                 s.get("publica", 1), s.get("activa", 1), s["creada"],
                 s.get("es_evento", 0), s.get("aforo", 0), s.get("premios_pct", ""),
                 s.get("tipo_juego", "linea_h1"), s.get("cupo_cartones", 0),
                 s.get("max_cartones", 0), s.get("fecha_partida", "") or "",
                 s.get("hora_partida", "") or "",
                 s.get("pais", "VE") or "VE", s.get("es_trabajo", 0)),
            )

    def actualizar_sala(self, id_: str, campos: dict) -> None:
        """Cambia solo los campos indicados de una sala (precio, aforo, premios…)."""
        permitidos = {"nombre", "modo", "precio_carton", "publica", "activa",
                      "es_evento", "aforo", "premios_pct", "tipo_juego",
                      "cupo_cartones", "max_cartones", "fecha_partida", "hora_partida",
                      "pais", "es_trabajo", "dueno"}
        asignar = {k: v for k, v in campos.items() if k in permitidos}
        if not asignar:
            return
        columnas = ", ".join(f"{k} = ?" for k in asignar)
        with self.transaccion() as c:
            c.execute(f"UPDATE salas SET {columnas} WHERE id = ?",
                      (*asignar.values(), id_))

    def sala(self, id_: str) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM salas WHERE id = ?", (id_,))

    def salas(self, incluir_inactivas: bool = False) -> list[sqlite3.Row]:
        if incluir_inactivas:
            return self._todos("SELECT * FROM salas ORDER BY rowid ASC")
        return self._todos("SELECT * FROM salas WHERE activa = 1 ORDER BY rowid ASC")

    def activar_sala(self, id_: str, activa: bool) -> None:
        with self.transaccion() as c:
            c.execute("UPDATE salas SET activa = ? WHERE id = ?", (int(activa), id_))

    # -- ajustes internos (marcas de migración) --

    def meta(self, clave: str) -> str | None:
        fila = self._uno("SELECT valor FROM meta WHERE clave = ?", (clave,))
        return fila["valor"] if fila else None

    def guardar_meta(self, clave: str, valor: str) -> None:
        with self.transaccion() as c:
            c.execute("INSERT INTO meta (clave, valor) VALUES (?,?)"
                      " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                      (clave, str(valor)))

    # -- billeteras de cripto --

    def guardar_billetera(self, correo: str, red: str, direccion: str) -> None:
        with self.transaccion() as c:
            c.execute("INSERT INTO billeteras (correo, red, direccion, creada)"
                      " VALUES (?,?,?,?)"
                      " ON CONFLICT(correo) DO UPDATE SET red = excluded.red,"
                      " direccion = excluded.direccion, creada = excluded.creada",
                      (correo, red, direccion, time.time()))

    def billetera(self, correo: str) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM billeteras WHERE correo = ?", (correo,))

    def borrar_billetera(self, correo: str) -> None:
        with self.transaccion() as c:
            c.execute("DELETE FROM billeteras WHERE correo = ?", (correo,))

    def guardar_carton(self, id_: str, partida: str, correo: str, numeros: str) -> None:
        with self.transaccion() as c:
            c.execute(
                "INSERT INTO cartones (id, partida, correo, numeros) VALUES (?,?,?,?)",
                (id_, partida, correo, numeros),
            )

    def cartones(self, partida: str) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM cartones WHERE partida = ?", (partida,))

    def borrar_carton(self, id_: str) -> None:
        with self.transaccion() as c:
            c.execute("DELETE FROM cartones WHERE id = ?", (id_,))

    def borrar_cartones_de(self, partida: str, correo: str) -> None:
        """Quita de una partida todos los cartones de un jugador."""
        with self.transaccion() as c:
            c.execute("DELETE FROM cartones WHERE partida = ? AND correo = ?", (partida, correo))

    # -- estadísticas del jugador --

    def resumen_jugador(self, correo: str) -> dict:
        """Números de un jugador: cartones, partidas, premios y neto.

        Todo sale de la tabla de movimientos (que ya guarda cada apuesta y cada
        premio) y de los cartones comprados, así que no hay que llevar la cuenta
        por separado ni puede descuadrar.
        """
        gastado = self._uno(
            "SELECT COALESCE(SUM(-centimos), 0) AS t FROM movimientos"
            " WHERE correo = ? AND tipo = 'apuesta'", (correo,))
        ganado = self._uno(
            "SELECT COALESCE(SUM(centimos), 0) AS t FROM movimientos"
            " WHERE correo = ? AND tipo = 'premio'", (correo,))
        premios_n = self._uno(
            "SELECT COUNT(*) AS n FROM movimientos WHERE correo = ? AND tipo = 'premio'",
            (correo,))
        cartones_n = self._uno(
            "SELECT COUNT(*) AS n FROM cartones WHERE correo = ?", (correo,))
        partidas_n = self._uno(
            "SELECT COUNT(DISTINCT partida) AS n FROM cartones WHERE correo = ?", (correo,))
        return {
            "cartones": int(cartones_n["n"]) if cartones_n else 0,
            "partidas": int(partidas_n["n"]) if partidas_n else 0,
            "premios_ganados": int(premios_n["n"]) if premios_n else 0,
            "total_apostado": int(gastado["t"]) if gastado else 0,
            "total_ganado": int(ganado["t"]) if ganado else 0,
        }

    def ranking(self, limite: int = 20) -> list[sqlite3.Row]:
        """Los jugadores que más han ganado, con lo apostado y el neto."""
        return self._todos(
            "SELECT correo,"
            " COALESCE(SUM(CASE WHEN tipo = 'premio' THEN centimos ELSE 0 END), 0) AS ganado,"
            " COALESCE(SUM(CASE WHEN tipo = 'apuesta' THEN -centimos ELSE 0 END), 0) AS apostado,"
            " COUNT(CASE WHEN tipo = 'premio' THEN 1 END) AS premios"
            " FROM movimientos GROUP BY correo"
            " HAVING SUM(CASE WHEN tipo = 'premio' THEN centimos ELSE 0 END) > 0"
            " ORDER BY ganado DESC LIMIT ?", (limite,))

    def ganadores_de(self, partida: str) -> list[sqlite3.Row]:
        """Los cartones de una partida que pertenecen al ganador (o ganadores)."""
        fila = self.partida(partida)
        if fila is None or not fila["ganador"]:
            return []
        return self._todos("SELECT * FROM cartones WHERE partida = ? AND correo = ?",
                           (partida, fila["ganador"]))
