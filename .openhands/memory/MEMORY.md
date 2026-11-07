# Proyecto: Bingo Pirámide 777

Plataforma de **bingo de 75 bolas** ORIGINAL del usuario (repo
`bingopiramide777/bingopiramide777`, rama `main`). Nace de la petición (rechazada)
de clonar `juegoactivo.com`; se acordó hacer algo propio. **NO copiar** nada de
Juegoactivo (ni diseño, ni textos, ni login de Facebook).

## Arquitectura
- `nucleo/` — común: `money.py` (céntimos enteros, formato `Bs 1.234,50`),
  `monedero.py` (**solo acepta céntimos int**, convierte en el borde),
  `usuarios.py` (PBKDF2-HMAC-SHA256 200k, bloqueo 5 intentos/15 min).
- `bingo/` — `cartones.py` (cartón 5x5 B-I-N-G-O, bombo 75, `PATRONES`),
  `sala.py` (partidas, venta, cantadas validadas contra bolas), `mesa.py`
  (une sala+monedero; reparto del bote 80 %).
- `web/servidor.py` — `http.server` puro. El estado vive en `servidor.juego`
  (clase `Juego`), NO en una global: así las pruebas se aíslan con `crear_servidor(puerto=0)`.
- `web/static/` — HTML/CSS/JS propios, sin librerías. Paleta morado+dorado+verde.
- Tests: **62**, `python3 -m unittest discover -s tests -t .` (necesita `tests/__init__.py`).

## Decisiones que importan
- El monedero y el motor **no mueven dinero juntos**: la mesa cobra y paga, y si
  el cobro falla se deshace la jugada/cartón. Nunca queda cartón vendido sin cobrar.
- Resolver/cantar dos veces **falla** (idempotencia por estado), no paga doble.
- El servidor no puede servir ficheros fuera de `static/` (se comprueba `..`).

## Pendiente antes de dinero real
Saldos en memoria (se pierden al reiniciar) → falta base de datos; falta panel de
administrador, límites de retiro, verificación de identidad y HTTPS.

## Aviso legal
En Venezuela las apuestas están sujetas a autorización. El usuario fue avisado.
