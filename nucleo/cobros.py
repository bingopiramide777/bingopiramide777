"""Sistema de cobro: todo el dinero que entra y sale, en un solo sitio.

Aquí se juntan los cobros que la app y el anfitrión hacen al jugador, para
poder verlos de un vistazo y —lo más importante— para comprobar que **ninguno
se cobra dos veces**. Esa comprobación es la razón de este módulo: el dinero
del proyecto se mueve en dos momentos distintos y hay dos "20 %" que se
confunden con facilidad.

Los cobros del proyecto:

1. **Comisión de depósito (20 %).** Se retiene UNA vez al acreditar un
   depósito, sobre lo que el jugador ingresa. Frena el lavado de dinero.
2. **Comisión de anfitrión.** Se cobra del bote al terminar cada partida, una
   sola vez por partida, y va a la cuenta del dueño de la sala:
   - sala de la casa: 0 % (todo el margen es de la app);
   - sala de jugador: 10 % para el anfitrión (la app el 20 %);
   - sala de trabajo ("Gana dinero desde casa"): 15 % para el anfitrión
     (la app el 5 %). El dueño es el jugador que trabaja y trae a la gente; su
     15 % va a SU cuenta.
3. **Comisión de padrino (referidos).** Se cobra de la parte de la app, una
   sola vez por partida y padrino.

Este módulo no mueve dinero: solo lo define, lo suma y lo audita. Quien mueve
el dinero de verdad es `Monedero` (a través de `Depositos` y `MesaBingo`).
"""

from __future__ import annotations

from .money import a_texto

# Porcentajes de referencia (los reales se leen de la sala y del entorno).
PCT_DEPOSITO = 20        # % que retiene la app al acreditar un depósito
PCT_APP_TRABAJO = 5      # % de la app en la sala de trabajo
PCT_ANFITRION_TRABAJO = 15  # % del anfitrión en la sala de trabajo


def _sala_de_partida(almacen, sala_id: str):
    return almacen.sala(sala_id) if sala_id else None


class Cobros:
    """Define, suma y audita todos los cobros del proyecto."""

    def __init__(self, almacen, salas=None, depositos=None) -> None:
        self.almacen = almacen
        self.salas = salas
        self.depositos = depositos

    # -- definición: qué se cobra y a quién --

    def definicion(self) -> list[dict]:
        """La tabla de cobros, en texto, para mostrarla en el panel."""
        pct_dep = self.depositos.config.comision_pct if self.depositos else PCT_DEPOSITO
        return [
            {
                "clave": "deposito",
                "titulo": "Comisión de depósito",
                "pct": pct_dep,
                "quien": "la app",
                "cuando": "al acreditar cada depósito (una sola vez)",
                "sobre": "lo que el jugador ingresa",
                "motivo": "anti-lavado: quien mete dinero deja su parte antes de sacarlo",
            },
            {
                "clave": "anfitrion_trabajo",
                "titulo": "Comisión del anfitrión (sala de trabajo)",
                "pct": PCT_ANFITRION_TRABAJO,
                "quien": "el dueño de la sala de trabajo",
                "cuando": "al cantar bingo, una sola vez por partida",
                "sobre": "el bote de la partida",
                "motivo": "es él quien trae a los jugadores a la sala de 'Gana desde casa'",
            },
            {
                "clave": "app_trabajo",
                "titulo": "Parte de la app (sala de trabajo)",
                "pct": PCT_APP_TRABAJO,
                "quien": "la app",
                "cuando": "al cantar bingo, una sola vez por partida",
                "sobre": "el bote de la partida",
                "motivo": "es lo único que deja esa sala a la casa (ganador 80 % + anfitrión 15 %)",
            },
            {
                "clave": "anfitrion_normal",
                "titulo": "Comisión del anfitrión (sala de jugador)",
                "pct": 10,
                "quien": "el dueño de la sala",
                "cuando": "al cantar bingo, una sola vez por partida",
                "sobre": "el bote de la partida",
                "motivo": "paga al anfitrión por organizar; la app se queda el 20 %",
            },
            {
                "clave": "padrino",
                "titulo": "Comisión de padrino (referidos)",
                "pct": None,   # lo pone el entorno; se rellena en totales()
                "quien": "el padrino que invitó al ganador",
                "cuando": "al cantar bingo, una sola vez por partida y padrino",
                "sobre": "la parte de la app en esa partida",
                "motivo": "premia traer jugadores; nunca toca el premio ni al anfitrión",
            },
        ]

    # -- totales: cuánto se ha cobrado de verdad --

    def totales(self) -> dict:
        """Lo cobrado hasta ahora, por concepto, sumado de los datos reales."""
        eco = self.salas.economia() if self.salas else {
            "botes": 0, "premios": 0, "comisiones": 0, "app": 0}
        dep_comision = self.depositos.comision_total() if self.depositos else 0
        dep_acreditado = sum(
            d["acreditado"] for d in self.almacen.depositos(estado="acreditado")) \
            if self.depositos else 0
        referidos = sum(int(f["centimos"]) for f in self.almacen.referidos())
        return {
            "deposito_pct": self.depositos.config.comision_pct if self.depositos else PCT_DEPOSITO,
            "deposito_comision": dep_comision,
            "deposito_acreditado": dep_acreditado,
            "anfitrion": eco.get("comisiones", 0),
            "app_bingo": eco.get("app", 0),
            "app_depositos": dep_comision,
            "app_total": eco.get("app", 0) + dep_comision,
            "padrinos": referidos,
            "botes": eco.get("botes", 0),
            "premios": eco.get("premios", 0),
        }

    # -- auditoría: ningún cobro se duplica --

    def auditar(self) -> dict:
        """Comprueba que ningún cobro se haya hecho dos veces.

        Es la razón de ser del módulo. Cada freno es el que ya usa el programa
        al cobrar de verdad; aquí solo se mira el resultado:
        - un depósito acreditado no puede volver a acreditarse (lo impide
          `resolver_deposito`, que solo toca depósitos en 'pendiente');
        - una comisión de anfitrión no puede pagarse dos veces por la misma
          partida (una partida terminada no vuelve a cantarse);
        - un padrino no puede cobrar dos veces por la misma partida (lo impide
          la clave única `(partida, padrino)` de la tabla `referidos`).
        """
        avisos: list[str] = []

        # 1) Depósitos: ninguna referencia acreditada dos veces.
        acreditados: dict[str, int] = {}
        for d in self.almacen.depositos(estado="acreditado"):
            clave = f"{d['referencia']}|{d['dia']}"
            acreditados[clave] = acreditados.get(clave, 0) + 1
        repetidos = {k: n for k, n in acreditados.items() if n > 1}
        if repetidos:
            avisos.append(f"Hay {len(repetidos)} depósito(s) acreditado(s) más de una vez.")

        # 2) Comisiones de anfitrión: una sola por partida terminada.
        #    Cada partida terminada se liquida una vez; se cuentan los movimientos
        #    de comisión de sala para detectar partidas repetidas.
        partidas_terminadas = [f["id"] for f in self.almacen.partidas(100000)
                               if f["estado"] == "terminada"]
        comisiones = {}
        for m in self.almacen.movimientos_por_motivo("comisión de sala"):
            comisiones[m["motivo"]] = comisiones.get(m["motivo"], 0) + 1
        repetidas = {k: n for k, n in comisiones.items() if n > 1}
        if repetidas:
            avisos.append(
                f"Hay {len(repetidas)} comisión(es) de anfitrión pagada(s) más de una vez "
                "en la misma partida.")

        # 3) Referidos: un padrino, una vez por partida (clave única).
        por_pareja = {}
        for f in self.almacen.referidos():
            clave = f"{f['partida']}|{f['padrino']}"
            por_pareja[clave] = por_pareja.get(clave, 0) + 1
        duplicados = {k: n for k, n in por_pareja.items() if n > 1}
        if duplicados:
            avisos.append(f"Hay {len(duplicados)} comisión(es) de padrino repetida(s).")

        return {
            "sin_duplicados": not avisos,
            "avisos": avisos,
            "depositos_acreditados": sum(acreditados.values()),
            "partidas_terminadas": len(partidas_terminadas),
            "referidos_anotados": sum(por_pareja.values()),
        }

    # -- vista para el panel --

    def resumen(self) -> dict:
        t = self.totales()
        a = self.auditar()
        def txt(v):
            return a_texto(v)
        return {
            "definicion": self.definicion(),
            "totales": {**t,
                        "deposito_comision_texto": txt(t["deposito_comision"]),
                        "deposito_acreditado_texto": txt(t["deposito_acreditado"]),
                        "anfitrion_texto": txt(t["anfitrion"]),
                        "app_bingo_texto": txt(t["app_bingo"]),
                        "app_depositos_texto": txt(t["app_depositos"]),
                        "app_total_texto": txt(t["app_total"]),
                        "padrinos_texto": txt(t["padrinos"]),
                        "botes_texto": txt(t["botes"]),
                        "premios_texto": txt(t["premios"])},
            "auditoria": a,
        }
