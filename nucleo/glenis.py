"""Glenis IA: la asistente que ayuda a llevar la cuenta de administración.

Habla con un modelo de lenguaje (Groq) y le da **herramientas** para consultar y
mover cosas de verdad: ver el resumen, revisar retiros, acreditar depósitos,
avisar de un ganador, ajustar un saldo.

Reglas de diseño, y son a propósito:

- **Glenis no inventa.** Si no puede comprobar algo, lo dice. Un asistente de
  dinero que se inventa cifras es peor que no tener asistente.
- **Lo que mueve dinero queda escrito.** Cada acción que toca saldos deja rastro
  en la base de datos y en el registro de Glenis, con quién lo pidió y cuándo.
- **El depósito no se acredita solo por una foto.** Glenis lo deja en cola con
  los datos que ha leído, y el administrador confirma. La IA ayuda; no firma.
- **La clave vive en `GROQ_API_KEY`**, nunca en el código.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
MODELO = "openai/gpt-oss-120b"

# Cloudflare delante de Groq bloquea el User-Agent por defecto de Python.
CABECERAS_BASE = {"Content-Type": "application/json", "User-Agent": "BingoPiramide777/1.0"}

INSTRUCCIONES = """Eres Glenis IA, la asistente de Bingo Pirámide 777. Ayudas a la
administración a llevar la cuenta: depósitos, retiros, ganadores, jugadores y saldos.

Cómo hablas: en español de Venezuela, cercano y directo, sin rodeos y sin sonar a robot.
Llamas al administrador por su nombre cuando lo sabes. Usas "tú".

Cómo trabajas:
- Cuando te pregunten algo de números, MIRA los datos con tus herramientas antes de
  responder. No te inventes nunca una cifra. Si no puedes comprobarlo, dilo claro.
- Antes de mover dinero (acreditar un depósito, ajustar un saldo), confirma en voz alta
  lo que vas a hacer y para quién. Si falta un dato, pregúntalo.
- Si algo te huele mal (un depósito enorme, un jugador que deposita y retira sin jugar,
  referencias repetidas), dilo. Es parte de tu trabajo.
- Para acreditar un depósito hace falta: correo del jugador, monto, referencia y fecha.
  Si falta la referencia o la fecha, PÍDELAS. No las inventes.
- Eres breve. Dos o tres frases. Nada de párrafos largos.
- Un administrador NO es un jugador. Cuando cuentes jugadores, cuenta solo las cuentas con
  rol 'jugador'. Si te preguntan cuántos jugadores hay, esa es la cifra.

Para llevar la cuenta de administración:
- Estado de cuenta de un jugador: usa 'estado_de_cuenta' (saldo, apostado, ganado, neto,
  cartones y premios). No lo confundas con 'buscar_jugador', que es la ficha rápida.
- Ganadores: usa 'listar_ganadores' para ver quién ganó y cuánto se le debe.
- Para acreditar un premio, saca primero los datos con 'datos_de_acreditacion' (correo,
  monto y referencia). Cuando el pago ya se hizo, anótalo con 'marcar_premio_pagado'.
- Datos de cobro: cada jugador puede dejar en su perfil a dónde quiere que le paguen
  (Pago Móvil, Nequi, MACH, Cash App o transferencia). Míralos con 'ver_datos_cobro'.
  Con 'preparar_pago_ganador' armas la orden de pago completa (a quién, cuánto, por dónde
  y la referencia). Esa orden la ejecuta una persona: tú NO mueves dinero real.
- Si un ganador no tiene datos de cobro, DILO: hay que pedírselos antes de pagarle.
- Resumen de pagos: usa 'reporte_de_pagos' para ver premios por acreditar, retiros
  pendientes y depósitos por acreditar de una vez.
- Cuentas de la administración: cada país tiene su cuenta donde cae el dinero que
  depositan los jugadores (Venezuela, Colombia, Chile y Estados Unidos). Míralas con
  'cuentas_admin'. Ojo: son las cuentas de la CASA, no de los jugadores. Si una sale
  sin configurar, avísalo: falta poner los datos reales.

Lo que NO haces:
- No pagas retiros por tu cuenta: eso lo autoriza y lo ejecuta la persona. Tú avisas.
- No mandas dinero a ningún banco ni pasarela. Tú preparas la orden; la persona paga.
- No prometes plazos que no puedas cumplir.
- No das datos de un jugador a otro.
"""


def _espera_del_error(texto: str) -> float | None:
    """Saca los segundos de espera de un error 429 de Groq.

    Groq dice "Please try again in 2.745s" o "... in 90ms". Se espera un poco más
    de lo que pide, para no volver a chocar.
    """
    if "429" not in texto:
        return None
    import re as _re

    if (m := _re.search(r"try again in ([\d.]+)s", texto)):
        return min(float(m.group(1)) + 0.6, 20.0)
    if (m := _re.search(r"try again in ([\d.]+)ms", texto)):
        return min(float(m.group(1)) / 1000 + 0.6, 20.0)
    return 3.0


class ErrorDeGlenis(Exception):
    """No se pudo hablar con la IA o la respuesta vino mal."""


@dataclass
class Respuesta:
    texto: str
    acciones: list[dict] = field(default_factory=list)
    pasos: int = 0


class Glenis:
    """El motor de la IA. Las herramientas las pasa quien lo construye."""

    def __init__(self, herramientas, ejecutor, clave: str | None = None,
                 modelo: str = MODELO, memoria_max: int = 8) -> None:
        self.clave = clave or os.environ.get("GROQ_API_KEY", "")
        self.modelo = modelo
        self.herramientas = herramientas      # lista de esquemas para la IA
        self.ejecutor = ejecutor              # función(nombre, argumentos) -> dict
        self.memoria_max = memoria_max

    @property
    def configurada(self) -> bool:
        return bool(self.clave)

    def conversar(self, mensajes: list[dict], nombre_admin: str = "") -> Respuesta:
        """Un turno de conversación. Ejecuta las herramientas que la IA pida.

        Da hasta 6 pasos: la IA puede mirar datos, luego mirar más, y por último
        contestar. Sin tope, un modelo mareado podría dar vueltas para siempre.
        """
        if not self.configurada:
            raise ErrorDeGlenis(
                "Glenis IA no tiene clave configurada. Añade GROQ_API_KEY en el entorno."
            )

        historial = [{"role": "system", "content": INSTRUCCIONES +
                      (f"\n\nHablas con {nombre_admin}." if nombre_admin else "")}]
        historial.extend(mensajes[-self.memoria_max:])

        acciones: list[dict] = []
        for paso in range(6):
            respuesta = self._pedir(historial)
            mensaje = respuesta["choices"][0]["message"]
            llamadas = mensaje.get("tool_calls") or []

            if not llamadas:
                return Respuesta(texto=(mensaje.get("content") or "").strip(),
                                 acciones=acciones, pasos=paso + 1)

            historial.append(mensaje)
            for llamada in llamadas:
                nombre = llamada["function"]["name"]
                try:
                    argumentos = json.loads(llamada["function"].get("arguments") or "{}")
                    if not isinstance(argumentos, dict):
                        argumentos = {}
                except ValueError:
                    argumentos = {}
                resultado = self.ejecutor(nombre, argumentos)
                acciones.append({"herramienta": nombre, "datos": resultado})
                historial.append({
                    "role": "tool",
                    "tool_call_id": llamada.get("id", ""),
                    "name": nombre,
                    "content": json.dumps(resultado, ensure_ascii=False, default=str)[:4000],
                })

        return Respuesta(texto="He dado demasiadas vueltas. ¿Puedes reformularlo?",
                         acciones=acciones, pasos=6)

    def _pedir(self, mensajes: list[dict], intentos: int = 3) -> dict:
        """Pide una respuesta, esperando si el plan gratuito se queda sin tokens.

        El plan gratuito de Groq limita los tokens por minuto. Sin esta espera,
        una pregunta con muchas herramientas falla con un 429 y el administrador
        ve un error en vez de una respuesta.
        """
        for intento in range(intentos):
            try:
                return self._pedir_una_vez(mensajes)
            except ErrorDeGlenis as exc:
                espera = _espera_del_error(str(exc))
                if espera is None or intento == intentos - 1:
                    raise
                time.sleep(espera)
        raise ErrorDeGlenis("La IA no respondió.")

    def _pedir_una_vez(self, mensajes: list[dict]) -> dict:
        cuerpo = {
            "model": self.modelo,
            "messages": mensajes,
            "tools": self.herramientas,
            "tool_choice": "auto",
            "temperature": 0.3,
            "max_tokens": 900,
        }
        peticion = urllib.request.Request(
            URL_GROQ, data=json.dumps(cuerpo).encode("utf-8"),
            headers={**CABECERAS_BASE, "Authorization": f"Bearer {self.clave}"},
        )
        try:
            with urllib.request.urlopen(peticion, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detalle = ""
            try:
                detalle = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:  # noqa: BLE001
                pass
            raise ErrorDeGlenis(f"La IA respondió con error {exc.code}. {detalle}".strip()) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ErrorDeGlenis("No se pudo contactar con la IA. ¿Hay internet?") from None


@dataclass
class Turno:
    """Un mensaje del registro de Glenis, para que quede constancia."""
    quien: str
    texto: str
    cuando: float
    acciones: list[dict] = field(default_factory=list)
