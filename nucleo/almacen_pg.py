"""Almacén sobre PostgreSQL, para no perder los datos al reiniciar.

El plan gratuito de Render borra el disco en cada despliegue, así que el fichero
SQLite se va con él. Este almacén guarda lo mismo en un Postgres, que sí aguanta
los reinicios.

No reescribe la lógica: hereda de `Almacen` y traduce al vuelo el poco SQL que
cambia entre SQLite y Postgres (`?` por `%s`, `INSERT OR IGNORE`, `rowid`). Así
las cuarenta y pico consultas se escriben una sola vez y no se separan con el
tiempo.

Se elige con la variable de entorno `DATABASE_URL` (la que pone Render al crear
una base de datos). Sin ella, la app sigue usando SQLite como siempre.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Iterator

from .almacen import Almacen

# El mismo esquema que en SQLite, con dos cambios que exige Postgres:
# - `REAL` pasa a `DOUBLE PRECISION` (los sellos de tiempo llevan milisegundos
#   y en 4 bytes se perderían).
# - `partidas` y `salas` llevan una columna `seq` que hace de `rowid`: Postgres
#   no tiene `rowid` y el código ordena por ahí para ver lo último primero.
ESQUEMA_PG = """
CREATE TABLE IF NOT EXISTS usuarios (
    correo  TEXT PRIMARY KEY,
    huella  TEXT NOT NULL,
    nombre  TEXT NOT NULL DEFAULT '',
    rol     TEXT NOT NULL DEFAULT 'jugador',
    activo  INTEGER NOT NULL DEFAULT 1,
    creado  DOUBLE PRECISION NOT NULL,
    comision_pct INTEGER NOT NULL DEFAULT -1,
    verificado INTEGER NOT NULL DEFAULT 1,
    pregunta TEXT NOT NULL DEFAULT '',
    respuesta_huella TEXT NOT NULL DEFAULT '',
    datos_cobro TEXT NOT NULL DEFAULT '',
    codigo_amigo TEXT NOT NULL DEFAULT '',
    referido_por TEXT NOT NULL DEFAULT '',
    foto TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_codigo ON usuarios(codigo_amigo)
    WHERE codigo_amigo <> '';

CREATE TABLE IF NOT EXISTS referidos (
    id       TEXT PRIMARY KEY,
    partida  TEXT NOT NULL,
    referido TEXT NOT NULL,
    padrino  TEXT NOT NULL,
    centimos BIGINT NOT NULL,
    cuando   DOUBLE PRECISION NOT NULL,
    UNIQUE(partida, padrino)
);
CREATE INDEX IF NOT EXISTS idx_referidos_padrino ON referidos(padrino, cuando);

CREATE TABLE IF NOT EXISTS cuentas (
    correo   TEXT PRIMARY KEY,
    centimos BIGINT NOT NULL DEFAULT 0 CHECK (centimos >= 0)
);

CREATE TABLE IF NOT EXISTS movimientos (
    id            TEXT PRIMARY KEY,
    correo        TEXT NOT NULL,
    tipo          TEXT NOT NULL,
    centimos      BIGINT NOT NULL,
    saldo_despues BIGINT NOT NULL,
    motivo        TEXT NOT NULL DEFAULT '',
    cuando        DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mov_correo ON movimientos(correo, cuando);

CREATE TABLE IF NOT EXISTS sesiones (
    token  TEXT PRIMARY KEY,
    correo TEXT NOT NULL,
    creada DOUBLE PRECISION NOT NULL,
    caduca DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS retiros (
    id          TEXT PRIMARY KEY,
    correo      TEXT NOT NULL,
    centimos    BIGINT NOT NULL,
    metodo      TEXT NOT NULL,
    detalles    TEXT NOT NULL DEFAULT '',
    estado      TEXT NOT NULL DEFAULT 'pendiente',
    pedido      DOUBLE PRECISION NOT NULL,
    revisado    DOUBLE PRECISION,
    revisado_por TEXT,
    nota        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_retiros_estado ON retiros(estado, pedido);

CREATE TABLE IF NOT EXISTS partidas (
    id             TEXT PRIMARY KEY,
    seq            BIGSERIAL,
    sala           TEXT NOT NULL DEFAULT '',
    patron         TEXT NOT NULL,
    precio_carton  BIGINT NOT NULL,
    estado         TEXT NOT NULL,
    bolas          TEXT NOT NULL DEFAULT '',
    ganador        TEXT,
    carton_ganador TEXT,
    premio         BIGINT NOT NULL DEFAULT 0,
    empezada       DOUBLE PRECISION,
    terminada      DOUBLE PRECISION,
    ganadores      TEXT NOT NULL DEFAULT '',
    plazas         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS depositos (
    id            TEXT PRIMARY KEY,
    correo        TEXT NOT NULL,
    centimos      BIGINT NOT NULL,
    metodo        TEXT NOT NULL,
    referencia    TEXT NOT NULL,
    banco         TEXT NOT NULL DEFAULT '',
    dia           TEXT NOT NULL,
    estado        TEXT NOT NULL DEFAULT 'pendiente',
    nota          TEXT NOT NULL DEFAULT '',
    pedido        DOUBLE PRECISION NOT NULL,
    revisado      DOUBLE PRECISION,
    revisado_por  TEXT,
    pais          TEXT NOT NULL DEFAULT 'VE',
    comision      BIGINT NOT NULL DEFAULT 0,
    acreditado    BIGINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_depositos ON depositos(estado, pedido);
CREATE UNIQUE INDEX IF NOT EXISTS idx_depositos_ref
    ON depositos(referencia, dia) WHERE estado != 'rechazado';

CREATE TABLE IF NOT EXISTS glenis (
    id        TEXT PRIMARY KEY,
    quien     TEXT NOT NULL,
    texto     TEXT NOT NULL,
    acciones  TEXT NOT NULL DEFAULT '',
    cuando    DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_glenis ON glenis(cuando);

CREATE TABLE IF NOT EXISTS codigos (
    id       TEXT PRIMARY KEY,
    correo   TEXT NOT NULL,
    huella   TEXT NOT NULL,
    intentos INTEGER NOT NULL DEFAULT 0,
    usado    INTEGER NOT NULL DEFAULT 0,
    creado   DOUBLE PRECISION NOT NULL,
    caduca   DOUBLE PRECISION NOT NULL,
    tipo     TEXT NOT NULL DEFAULT 'recuperacion'
);
CREATE INDEX IF NOT EXISTS idx_codigos_correo ON codigos(correo, usado, creado);

CREATE TABLE IF NOT EXISTS salas (
    id             TEXT PRIMARY KEY,
    seq            BIGSERIAL,
    nombre         TEXT NOT NULL,
    modo           TEXT NOT NULL,
    precio_carton  BIGINT NOT NULL,
    dueno          TEXT NOT NULL DEFAULT '',
    publica        INTEGER NOT NULL DEFAULT 1,
    activa         INTEGER NOT NULL DEFAULT 1,
    creada         DOUBLE PRECISION NOT NULL,
    es_evento      INTEGER NOT NULL DEFAULT 0,
    aforo          INTEGER NOT NULL DEFAULT 0,
    premios_pct    TEXT NOT NULL DEFAULT '',
    tipo_juego     TEXT NOT NULL DEFAULT '',
    cupo_cartones  INTEGER NOT NULL DEFAULT 0,
    max_cartones   INTEGER NOT NULL DEFAULT 0,
    fecha_partida  TEXT NOT NULL DEFAULT '',
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
    creada    DOUBLE PRECISION NOT NULL
);
"""

_INSERT_OR_IGNORE = re.compile(r"INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE)
_ROWID = re.compile(r"\browid\b", re.IGNORECASE)


def traducir(sql: str) -> str:
    """Convierte una consulta escrita para SQLite en una que entiende Postgres.

    Solo cambia lo imprescindible: los marcadores, el `INSERT OR IGNORE` y el
    `rowid`. El `ON CONFLICT ... DO UPDATE` de SQLite y el de Postgres son
    idénticos, así que no se toca.
    """
    sql = sql.replace("?", "%s")
    if _INSERT_OR_IGNORE.search(sql):
        sql = _INSERT_OR_IGNORE.sub("INSERT INTO", sql).rstrip().rstrip(";")
        sql += " ON CONFLICT DO NOTHING"
    return _ROWID.sub("seq", sql)


class _Conexion:
    """Envuelve la conexión para traducir el SQL al vuelo.

    Los métodos heredados de `Almacen` escriben `?` y `rowid`; aquí se traducen
    justo antes de salir, de modo que el resto del programa no sabe (ni le
    importa) sobre qué base de datos corre.
    """

    def __init__(self, con) -> None:
        self._con = con

    def execute(self, sql: str, args: tuple = ()):
        return self._con.execute(traducir(sql), args)

    def __getattr__(self, nombre):
        return getattr(self._con, nombre)


class AlmacenPG(Almacen):
    """El almacén sobre PostgreSQL. Misma API que el de SQLite."""

    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self.ruta = _dsn_visible(dsn)
        import threading
        self._candado = threading.RLock()
        self._con = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
        with self._con.transaction():
            self._con.execute(ESQUEMA_PG)
        self._migrar()

    @contextmanager
    def transaccion(self) -> Iterator[_Conexion]:
        with self._candado:
            with self._con.transaction():
                yield _Conexion(self._con)

    def _uno(self, sql: str, args: tuple = ()):
        with self._candado:
            return _Conexion(self._con).execute(sql, args).fetchone()

    def _todos(self, sql: str, args: tuple = ()) -> list:
        with self._candado:
            return list(_Conexion(self._con).execute(sql, args).fetchall())

    def cerrar(self) -> None:
        with self._candado:
            self._con.close()

    def _columnas(self, tabla: str) -> set[str]:
        filas = self._todos(
            "SELECT column_name AS name FROM information_schema.columns WHERE table_name = %s",
            (tabla,),
        )
        return {f["name"] for f in filas}

    def _migrar(self) -> None:
        """Añade columnas que falten en una base creada con una versión anterior."""
        pendientes = {
            "usuarios": (("pregunta", "TEXT NOT NULL DEFAULT ''"),
                         ("respuesta_huella", "TEXT NOT NULL DEFAULT ''"),
                         ("comision_pct", "INTEGER NOT NULL DEFAULT -1"),
                         ("verificado", "INTEGER NOT NULL DEFAULT 1"),
                         ("datos_cobro", "TEXT NOT NULL DEFAULT ''"),
                         ("codigo_amigo", "TEXT NOT NULL DEFAULT ''"),
                         ("referido_por", "TEXT NOT NULL DEFAULT ''"),
                         ("foto", "TEXT NOT NULL DEFAULT ''")),
            "codigos": (("tipo", "TEXT NOT NULL DEFAULT 'recuperacion'"),),
            "partidas": (("sala", "TEXT NOT NULL DEFAULT ''"),
                         ("ganadores", "TEXT NOT NULL DEFAULT ''"),
                         ("plazas", "INTEGER NOT NULL DEFAULT 1")),
            "salas": (("es_evento", "INTEGER NOT NULL DEFAULT 0"),
                      ("aforo", "INTEGER NOT NULL DEFAULT 0"),
                      ("premios_pct", "TEXT NOT NULL DEFAULT ''"),
                      ("tipo_juego", "TEXT NOT NULL DEFAULT ''"),
                      ("cupo_cartones", "INTEGER NOT NULL DEFAULT 0"),
                      ("max_cartones", "INTEGER NOT NULL DEFAULT 0"),
                      ("fecha_partida", "TEXT NOT NULL DEFAULT ''"),
                      ("pais", "TEXT NOT NULL DEFAULT 'VE'"),
                      ("es_trabajo", "INTEGER NOT NULL DEFAULT 0")),
            "depositos": (("pais", "TEXT NOT NULL DEFAULT 'VE'"),
                          ("comision", "BIGINT NOT NULL DEFAULT 0"),
                          ("acreditado", "BIGINT NOT NULL DEFAULT 0")),
        }
        for tabla, columnas in pendientes.items():
            existentes = self._columnas(tabla)
            for nombre, definicion in columnas:
                if nombre not in existentes:
                    with self.transaccion() as c:
                        c.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {definicion}")


def _dsn_visible(dsn: str) -> str:
    """El DSN sin la contraseña, para poder imprimirlo en los registros."""
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", dsn)


def es_postgres(dsn: str) -> bool:
    return bool(dsn) and dsn.split("://", 1)[0] in ("postgres", "postgresql")


def abrir_almacen(dsn: str | None = None, ruta: str | None = None) -> Almacen:
    """Elige el almacén según el entorno.

    Si hay `DATABASE_URL` (Postgres) se usa ese; si no, el fichero SQLite de
    siempre. Así en local y en las pruebas nada cambia, y en producción con una
    base de datos Postgres los datos sobreviven a los despliegues.
    """
    import os

    dsn = dsn or os.environ.get("DATABASE_URL", "")
    if es_postgres(dsn):
        return AlmacenPG(dsn)
    return Almacen(ruta or os.environ.get("BINGO_DB", "bingo777.db"))
