"""Envío de correos, con la cuenta configurada por variables de entorno.

La clave NO vive en el código: se lee de `GMAIL_APP_PASSWORD`. Y no es la
contraseña normal de Gmail, sino una **contraseña de aplicación** que se genera
en myaccount.google.com/apppasswords.

Si no hay clave configurada, el correo no se envía: se imprime el código por
consola para poder probar, y se avisa. Así el programa nunca miente diciendo que
ha mandado un correo que no ha mandado.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

SERVIDOR_SMTP = "smtp.gmail.com"
PUERTO_SMTP = 587


class ErrorDeCorreo(Exception):
    """No se pudo enviar el correo."""


class Correo:
    def __init__(self, usuario: str | None = None, clave: str | None = None,
                 remitente: str | None = None) -> None:
        self.usuario = usuario or os.environ.get("GMAIL_USER", "")
        self.clave = clave or os.environ.get("GMAIL_APP_PASSWORD", "")
        self.remitente = remitente or self.usuario

    @property
    def configurado(self) -> bool:
        return bool(self.usuario and self.clave)

    def enviar(self, destino: str, asunto: str, texto: str, html: str | None = None) -> bool:
        """Manda un correo. Devuelve si se pudo enviar de verdad.

        Si no hay cuenta configurada, imprime el contenido por consola (útil para
        probar) y devuelve False: quien llama sabrá que el jugador no lo ha
        recibido y podrá decírselo.
        """
        if not self.configurado:
            print(f"\n  [CORREO NO CONFIGURADO] Para: {destino}\n  Asunto: {asunto}\n{texto}\n")
            return False

        mensaje = EmailMessage()
        mensaje["From"] = f"Bingo Pirámide 777 <{self.remitente}>"
        mensaje["To"] = destino
        mensaje["Subject"] = asunto
        mensaje.set_content(texto)
        if html:
            mensaje.add_alternative(html, subtype="html")

        try:
            with smtplib.SMTP(SERVIDOR_SMTP, PUERTO_SMTP, timeout=15) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(self.usuario, self.clave)
                smtp.send_message(mensaje)
            return True
        except (smtplib.SMTPException, OSError) as exc:
            # El error puede traer la clave en el texto; no se imprime tal cual.
            raise ErrorDeCorreo(f"No se pudo enviar el correo ({type(exc).__name__}).") from None

    def enviar_codigo(self, destino: str, codigo: str, minutos: int) -> bool:
        asunto = f"Tu código para Bingo Pirámide 777: {codigo}"
        texto = (
            f"Tu código para recuperar la cuenta es:\n\n    {codigo}\n\n"
            f"Caduca en {minutos} minutos y solo se puede usar una vez.\n"
            "Si no has pedido tú este código, ignora este mensaje: nadie puede\n"
            "entrar en tu cuenta sin él.\n\n"
            "— Bingo Pirámide 777"
        )
        html = f"""<div style="font-family:Arial,sans-serif;background:#17082e;color:#fdf6e3;padding:28px;border-radius:14px">
  <h2 style="color:#f7c948;margin:0 0 6px">Bingo Pirámide 777</h2>
  <p style="color:#b9a9d4;margin:0 0 18px">Somos la pepa del queso</p>
  <p>Tu código para recuperar la cuenta es:</p>
  <p style="font-size:38px;font-weight:900;letter-spacing:.18em;color:#f7c948;margin:10px 0">{codigo}</p>
  <p style="color:#b9a9d4;font-size:13px">Caduca en {minutos} minutos y solo se puede usar una vez.<br>
  Si no has pedido tú este código, ignora este mensaje.</p>
</div>"""
        return self.enviar(destino, asunto, texto, html)

    def enviar_verificacion(self, destino: str, codigo: str, minutos: int) -> bool:
        asunto = f"Confirma tu cuenta de Bingo Pirámide 777: {codigo}"
        texto = (
            f"¡Bienvenido a Bingo Pirámide 777!\n\n"
            f"Tu código para confirmar el correo es:\n\n    {codigo}\n\n"
            f"Caduca en {minutos} minutos y solo se puede usar una vez.\n"
            "Si no has creado tú esta cuenta, ignora este mensaje.\n\n"
            "— Bingo Pirámide 777"
        )
        html = f"""<div style="font-family:Arial,sans-serif;background:#17082e;color:#fdf6e3;padding:28px;border-radius:14px">
  <h2 style="color:#f7c948;margin:0 0 6px">Bingo Pirámide 777</h2>
  <p style="color:#b9a9d4;margin:0 0 18px">Somos la pepa del queso</p>
  <p>¡Bienvenido! Tu código para confirmar el correo es:</p>
  <p style="font-size:38px;font-weight:900;letter-spacing:.18em;color:#f7c948;margin:10px 0">{codigo}</p>
  <p style="color:#b9a9d4;font-size:13px">Caduca en {minutos} minutos y solo se puede usar una vez.<br>
  Si no has creado tú esta cuenta, ignora este mensaje.</p>
</div>"""
        return self.enviar(destino, asunto, texto, html)
