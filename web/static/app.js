/* Bingo Pirámide 777 — interfaz. Sin dependencias: JavaScript a pelo. */

const $ = (sel) => document.querySelector(sel);
const CLAVE_TOKEN = "bp777_token";

let token = localStorage.getItem(CLAVE_TOKEN) || "";
let esAdmin = false;
let carton = null;
let misCartones = [];          // todos los cartones comprados en la partida
let automarcar = false;        // marca solo las bolas que salgan
let cuentaAtras = null;        // temporizador de la cuenta atrás de la partida

/* --- peticiones --- */

async function pedir(ruta, opciones = {}) {
  const cabeceras = { "Content-Type": "application/json" };
  if (token) cabeceras["Authorization"] = "Bearer " + token;
  const respuesta = await fetch(ruta, { ...opciones, headers: cabeceras });
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) throw new Error(datos.error || "Algo ha ido mal.");
  return datos;
}

const get = (ruta) => pedir(ruta);
const post = (ruta, cuerpo) => pedir(ruta, { method: "POST", body: JSON.stringify(cuerpo || {}) });

/* --- avisos --- */

let temporizador;
function avisar(mensaje, tipo = "") {
  const caja = $("#brindis");
  caja.textContent = mensaje;
  caja.className = "brindis" + (tipo ? " brindis--" + tipo : "");
  caja.hidden = false;
  clearTimeout(temporizador);
  temporizador = setTimeout(() => (caja.hidden = true), 3600);
}

/* --- dibujo de cartones --- */

function pintarCarton(destino, numeros, marcados = []) {
  const rejilla = $(destino);
  rejilla.innerHTML = "";
  const clave = new Set(marcados.map(([f, c]) => f + "," + c));
  for (let f = 0; f < 5; f++) {
    for (let c = 0; c < 5; c++) {
      const celda = document.createElement("div");
      celda.className = "celda";
      const esLibre = f === 2 && c === 2;
      if (esLibre) {
        celda.classList.add("celda--libre");
        celda.textContent = "LIBRE";
      } else {
        celda.textContent = numeros[f][c];
      }
      if (clave.has(f + "," + c) || esLibre) celda.classList.add("celda--marcada");
      rejilla.appendChild(celda);
    }
  }
}

function pintarCartonDemo() {
  const numeros = [
    [3, 18, 33, 47, 62],
    [7, 22, 39, 51, 70],
    [11, 27, 0, 55, 74],
    [14, 29, 41, 58, 68],
    [1, 16, 44, 49, 66],
  ];
  pintarCarton("#carton-demo", numeros, [[0, 0], [0, 2], [1, 1], [3, 4], [4, 0]]);
}

/* --- sesión --- */

function pintarSesion() {
  const caja = $("#sesion");
  caja.innerHTML = "";
  // La portada cambia según haya sesión o no: acceso o entrar a jugar.
  const acceso = $("#portada-acceso");
  const jugar = $("#portada-jugar");
  if (acceso && jugar) {
    acceso.hidden = !!token;
    jugar.hidden = !token;
  }
  if (token) {
    const correo = document.createElement("span");
    correo.textContent = localStorage.getItem("bp777_correo") || "";
    correo.style.color = "var(--gris)";
    caja.append(correo);
    // El enlace al panel depende del estado real de esta sesión, no de nada
    // guardado antes: si entras con otra cuenta, desaparece solo.
    if (esAdmin) {
      const panel = document.createElement("a");
      panel.className = "boton boton--fantasma";
      panel.href = "/admin";
      panel.style.padding = ".4rem 1rem";
      panel.textContent = "Panel";
      caja.appendChild(panel);
    }
    const salir = document.createElement("button");
    salir.className = "boton boton--fantasma";
    salir.textContent = "Salir";
    salir.style.padding = ".4rem 1rem";
    salir.onclick = () => cerrarSesion();
    caja.append(salir);
  } else {
    const entrar = document.createElement("button");
    entrar.className = "boton boton--principal";
    entrar.style.padding = ".45rem 1.1rem";
    entrar.textContent = "Entrar";
    entrar.onclick = () => abrirAcceso("entrar");
    caja.appendChild(entrar);
  }
}

/* Borra la sesión de este dispositivo. El panel de administración es una página
   aparte: nunca se recuerda aquí, así que este cierre no afecta a nadie más. */
function cerrarSesion() {
  try { post("/api/salir"); } catch (e) { /* da igual */ }
  localStorage.removeItem(CLAVE_TOKEN);
  localStorage.removeItem("bp777_correo");
  localStorage.removeItem("bp777_admin");
  token = "";
  location.reload();
}

/* --- diálogo de acceso --- */

let preguntas = [];

function abrirAcceso(modo) {
  const cabeceras = {
    entrar: ["Entrar", "Tu correo y tu contraseña. Nada de redes sociales."],
    registrar: ["Crear cuenta", "Regístrate con tu correo. La contraseña, mínimo 8 caracteres."],
    recuperar: ["Recuperar la cuenta", "Te mandamos un código al correo para poner una contraseña nueva."],
  };
  const [titulo, ayuda] = cabeceras[modo] || cabeceras.entrar;

  const campos = {
    entrar: `
      <label>Correo<input type="email" name="correo" required placeholder="tu@correo.com" autocomplete="email"></label>
      <label>Contraseña<input type="password" name="clave" required placeholder="••••••••" autocomplete="current-password"></label>`,
    registrar: `
      <label>Nombre<input type="text" name="nombre" placeholder="Cómo te llamas"></label>
      <label>Correo<input type="email" name="correo" required placeholder="tu@correo.com" autocomplete="email"></label>
      <label>Contraseña<input type="password" name="clave" required minlength="8" placeholder="••••••••" autocomplete="new-password"></label>
      <label>Pregunta secreta (para recuperar la cuenta)
        <select name="pregunta"><option value="">— Sin pregunta —</option></select>
      </label>
      <label>Tu respuesta<input type="text" name="respuesta" placeholder="Solo la sabes tú"></label>`,
    recuperar: `
      <label>Correo<input type="email" name="correo" required placeholder="tu@correo.com" autocomplete="email"></label>
      <button class="boton boton--principal" type="submit" id="btn-enviar-codigo">Enviar código</button>
      <div id="paso-codigo" hidden>
        <label>Código de 6 cifras<input type="text" name="codigo" inputmode="numeric" maxlength="6" placeholder="000000"></label>
        <label>Contraseña nueva<input type="password" name="clave" minlength="8" placeholder="••••••••" autocomplete="new-password"></label>
        <button class="boton boton--principal" type="submit" id="btn-cambiar-codigo">Cambiar contraseña</button>
      </div>
      <p class="ayuda">¿Prefieres tu pregunta secreta?
        <button type="button" class="enlace" id="usar-pregunta">Usar la pregunta</button></p>
      <div id="paso-pregunta" hidden>
        <label>Pregunta<input type="text" name="pregunta_mostrada" readonly></label>
        <label>Tu respuesta<input type="text" name="respuesta" placeholder="Tu respuesta"></label>
        <label>Contraseña nueva<input type="password" name="clave2" minlength="8" placeholder="••••••••" autocomplete="new-password"></label>
        <button class="boton boton--principal" type="submit" id="btn-cambiar-pregunta">Cambiar contraseña</button>
      </div>`,
  };

  $("#dialogo-contenido").innerHTML = `
    <h2>${titulo}</h2>
    <p style="color:var(--gris);font-size:.9rem">${ayuda}</p>
    <form id="form-acceso">${campos[modo]}</form>
    <p class="dialogo__cambio">
      ${modo === "entrar" ? '¿No tienes cuenta? <button id="ir-registrar">Créala</button> · <button id="ir-recuperar">Olvidé mi contraseña</button>'
        : '<button id="ir-entrar">Volver a entrar</button>'}
    </p>`;
  $("#dialogo").hidden = false;
  $("#dialogo-cerrar").onclick = () => ($("#dialogo").hidden = true);
  const ir = (sel, m) => { const b = $(sel); if (b) b.onclick = () => abrirAcceso(m); };
  ir("#ir-registrar", "registrar");
  ir("#ir-entrar", "entrar");
  ir("#ir-recuperar", "recuperar");

  if (modo === "registrar") {
    const sel = $("#form-acceso select[name=pregunta]");
    preguntas.forEach((p) => {
      const o = document.createElement("option");
      o.value = p; o.textContent = p;
      sel.appendChild(o);
    });
  }

  if (modo === "recuperar") {
    const form = $("#form-acceso");
    const correoDe = () => form.querySelector("[name=correo]").value.trim();
    $("#btn-enviar-codigo").onclick = async (e) => {
      e.preventDefault();
      if (!correoDe()) return avisar("Escribe tu correo.", "error");
      try {
        const res = await post("/api/recuperar/codigo", { correo: correoDe() });
        $("#paso-codigo").hidden = false;
        avisar(res.mensaje, res.enviado ? "bien" : "");
      } catch (err) { avisar(err.message, "error"); }
    };
    $("#btn-cambiar-codigo").onclick = async (e) => {
      e.preventDefault();
      const codigo = form.querySelector("[name=codigo]").value.trim();
      const clave = form.querySelector("#paso-codigo [name=clave]").value;
      try {
        const res = await post("/api/recuperar/codigo/cambiar", { correo: correoDe(), codigo, clave });
        $("#dialogo").hidden = true;
        avisar(res.mensaje, "bien");
        abrirAcceso("entrar");
      } catch (err) { avisar(err.message, "error"); }
    };
    $("#usar-pregunta").onclick = async (e) => {
      e.preventDefault();
      if (!correoDe()) return avisar("Escribe tu correo primero.", "error");
      try {
        const res = await post("/api/recuperar/pregunta", { correo: correoDe() });
        form.querySelector("[name=pregunta_mostrada]").value = res.pregunta;
        $("#paso-pregunta").hidden = false;
      } catch (err) { avisar(err.message, "error"); }
    };
    $("#btn-cambiar-pregunta").onclick = async (e) => {
      e.preventDefault();
      const respuesta = form.querySelector("#paso-pregunta [name=respuesta]").value;
      const clave = form.querySelector("#paso-pregunta [name=clave2]").value;
      try {
        const res = await post("/api/recuperar/pregunta/cambiar",
                               { correo: correoDe(), respuesta, clave });
        $("#dialogo").hidden = true;
        avisar(res.mensaje, "bien");
        abrirAcceso("entrar");
      } catch (err) { avisar(err.message, "error"); }
    };
    return;
  }

  $("#form-acceso").onsubmit = async (e) => {
    e.preventDefault();
    const datos = Object.fromEntries(new FormData(e.target));
    try {
      if (modo === "entrar") {
        const res = await post("/api/entrar", datos);
        token = res.token;
        localStorage.setItem(CLAVE_TOKEN, token);
        localStorage.setItem("bp777_correo", res.correo);
        localStorage.setItem("bp777_admin", res.admin ? "1" : "0");
        $("#dialogo").hidden = true;
        avisar("Bienvenido de nuevo.", "bien");
        pintarSesion();
        refrescarTodo();
        refrescarRetiros();
  refrescarDepositos();
      } else {
        await post("/api/registro", datos);
        avisar("Cuenta creada. Ahora entra.", "bien");
        abrirAcceso("entrar");
      }
    } catch (err) {
      avisar(err.message, "error");
    }
  };
}

/* --- depósitos --- */

async function refrescarDepositos() {
  const caja = $("#mis-depositos");
  if (!caja) return;
  if (!token) { caja.innerHTML = ""; return; }
  try {
    const res = await get("/api/depositos");
    if (!res.depositos.length) {
      caja.innerHTML = '<p class="ayuda">Todavía no has anotado ningún pago.</p>';
      return;
    }
    caja.innerHTML = `
      <h3 class="tabla__titulo">Mis pagos</h3>
      <div class="tabla-scroll"><table class="tabla">
        <thead><tr><th>Monto</th><th>Referencia</th><th>Día</th><th>Estado</th></tr></thead>
        <tbody>${res.depositos.map((d) => `
          <tr><td>${d.importe_texto}</td><td>${d.referencia}</td><td>${d.dia}</td>
          <td><span class="etiqueta etiqueta--${d.estado}">${
            { pendiente: "En revisión", acreditado: "Acreditado", rechazado: "Rechazado" }[d.estado]
            || d.estado}</span></td></tr>`).join("")}
        </tbody></table></div>`;
  } catch (err) { /* sin sesión: no se muestra nada */ }
}

/* Recargar saldo ya no se hace a mano: el jugador declara un pago y la
   administración lo revisa y lo acredita. */
function abrirDeposito() {
  const bancos = (configRetiro && configRetiro.bancos) || [];
  const cuenta = (configRetiro && configRetiro.cuenta_pago) || {};
  const hoy = new Date().toISOString().slice(0, 10);
  const bloqueCuenta = cuenta.configurada
    ? `<div class="cuenta-pago">
         <p class="cuenta-pago__titulo">Paga a esta cuenta</p>
         <p class="cuenta-pago__linea"><span>Banco</span><strong>${cuenta.banco}</strong></p>
         <p class="cuenta-pago__linea"><span>Teléfono</span>
           <strong class="mono">${cuenta.telefono}</strong>
           <button type="button" class="boton boton--fantasma boton--mini"
                   data-copiar="${cuenta.telefono}">Copiar</button></p>
         <p class="cuenta-pago__linea"><span>Cédula</span>
           <strong class="mono">${cuenta.cedula}</strong>
           <button type="button" class="boton boton--fantasma boton--mini"
                   data-copiar="${cuenta.cedula}">Copiar</button></p>
         ${cuenta.titular
           ? `<p class="cuenta-pago__linea"><span>Titular</span><strong>${cuenta.titular}</strong></p>`
           : ""}
       </div>`
    : "";
  $("#dialogo-contenido").innerHTML = `
    <h2>Recargar saldo</h2>
    ${bloqueCuenta}
    <p style="color:var(--gris);font-size:.9rem">
      Haz tu pago y anótalo aquí. Lo revisamos y te lo acreditamos enseguida.
      Mínimo ${configRetiro ? configRetiro.deposito_minimo_texto : ""}.</p>
    <form id="form-deposito">
      <label>Monto (Bs)
        <input type="text" name="importe" inputmode="decimal" placeholder="Bs 100,00" required>
      </label>
      <label>Método
        <select name="metodo">
          <option value="pago_movil">Pago móvil</option>
          <option value="transferencia">Transferencia</option>
        </select>
      </label>
      <label>Banco
        <select name="banco">${bancos.map((b) => `<option value="${b}">${b}</option>`).join("")}</select>
      </label>
      <label>Referencia
        <input type="text" name="referencia" placeholder="Número de referencia" required>
      </label>
      <label>Día del pago
        <input type="text" name="dia" value="${hoy}" placeholder="AAAA-MM-DD">
      </label>
      <button class="boton boton--principal boton--alto" type="submit">Anotar mi pago</button>
    </form>`;
  $("#dialogo").hidden = false;
  $("#dialogo-cerrar").onclick = () => ($("#dialogo").hidden = true);
  $("#dialogo-contenido").querySelectorAll("[data-copiar]").forEach((b) =>
    (b.onclick = async () => {
      try { await navigator.clipboard.writeText(b.dataset.copiar); avisar("Copiado.", "bien"); }
      catch (err) { avisar("Cópialo a mano.", "error"); }
    }));
  $("#form-deposito").onsubmit = async (e) => {
    e.preventDefault();
    const datos = Object.fromEntries(new FormData(e.target));
    try {
      const res = await post("/api/deposito", datos);
      $("#dialogo").hidden = true;
      avisar(res.mensaje, "bien");
      refrescarDepositos();
    } catch (err) { avisar(err.message, "error"); }
  };
}

/* --- salas --- */

let salaActual = "";
let salasDisponibles = [];

async function cargarSalas() {
  const caja = $("#lista-salas");
  if (!caja) return;
  try {
    const res = await get("/api/salas");
    salasDisponibles = res.salas;
    caja.innerHTML = salasDisponibles.map((s) => s.es_evento
      ? `<button class="sala-tarjeta sala-tarjeta--evento ${s.id === salaActual ? "sala-tarjeta--activa" : ""}"
                 data-sala="${s.id}">
           <span class="sala-tarjeta__etiqueta">Evento</span>
           <div class="sala-tarjeta__nombre">${s.nombre}</div>
           <div class="sala-tarjeta__modo">${nombreModo(s.modo)}</div>
           <div class="sala-tarjeta__precio">Cartón ${s.precio_texto}</div>
           <div class="sala-tarjeta__dueno">La administración pone el aforo y los premios</div>
         </button>`
      : `<button class="sala-tarjeta ${s.id === salaActual ? "sala-tarjeta--activa" : ""}"
                 data-sala="${s.id}">
           <div class="sala-tarjeta__nombre">${s.nombre}</div>
           <div class="sala-tarjeta__modo">${nombreModo(s.modo)}</div>
           <div class="sala-tarjeta__precio">Cartón ${s.precio_texto}</div>
           ${s.es_de_jugador ? `<div class="sala-tarjeta__dueno">Sala de ${s.dueno}</div>`
                             : '<div class="sala-tarjeta__dueno">Sala de la casa</div>'}
         </button>`).join("");
    caja.querySelectorAll("[data-sala]").forEach((b) =>
      (b.onclick = () => entrarASala(b.dataset.sala)));
    const evento = salasDisponibles.find((s) => s.es_evento);
    pintarEvento(evento ? evento.id : "");
    if (!salaActual && salasDisponibles.length) {
      await entrarASala(salasDisponibles[0].id);
    }
  } catch (err) { /* sin salas aún */ }
}

/* El evento Lago de Maracaibo: aforo, bote y premios por puesto. */
async function pintarEvento(salaId) {
  const caja = $("#evento-info");
  if (!caja) return;
  if (!salaId) { caja.innerHTML = ""; return; }
  try {
    const e = await get("/api/evento");
    const premios = (e.premios || []).map((p) => `
      <div class="premio">
        <div class="premio__puesto">${NOMBRES_PUESTO[p.puesto - 1] || p.puesto + "º"}</div>
        <div class="premio__importe">${p.premio_texto}</div>
        <div class="premio__pct">${p.pct_texto} del bote</div>
      </div>`).join("");
    caja.innerHTML = `
      <div class="evento">
        <div class="evento__cabecera">
          <h3 class="evento__titulo">${e.nombre}</h3>
          <span class="evento__aforo ${e.llena ? "evento__aforo--lleno" : ""}">
            ${e.llena ? "Aforo completo" : e.jugadores + " / " + (e.aforo || "∞") + " jugadores"}
          </span>
        </div>
        <p class="evento__bote">Cartón ${e.precio_texto} · Bote acumulado:
          <strong>${e.bote_texto}</strong></p>
        <div class="evento__premios">${premios || '<p class="ayuda">Sin premios configurados.</p>'}</div>
      </div>`;
  } catch (err) { caja.innerHTML = ""; }
}

const NOMBRES_PUESTO = ["Primer lugar", "Segundo lugar", "Tercer lugar"];

function nombreModo(modo) {
  return { normal: "Normal", carton_lleno: "Cartón lleno", competencia: "Competencia" }[modo]
    || modo;
}

async function entrarASala(id) {
  try {
    const res = await post("/api/sala/entrar", { sala: id });
    salaActual = id;
    document.querySelectorAll("[data-sala]").forEach((b) =>
      b.classList.toggle("sala-tarjeta--activa", b.dataset.sala === id));
    carton = null;
    const caja = $("#carton-jugador");
    if (caja) caja.innerHTML = '<p class="vacio">Todavía no tienes cartón.</p>';
    const botonBingo = $("#btn-bingo");
    if (botonBingo) botonBingo.disabled = true;
    refrescarPartida();
  } catch (err) { avisar(err.message, "error"); }
}

async function cargarMisSalas() {
  const caja = $("#tabla-mis-salas");
  if (!caja) return;
  if (!token) { caja.innerHTML = '<p class="ayuda">Entra para crear tus salas.</p>'; return; }
  try {
    const res = await get("/api/mis-salas");
    const g = res.ganancias;
    const p = $("#ganancias-pastilla");
    if (p) p.textContent = "Ganas " + g.anfitrion_texto;
    if (!res.salas.length) {
      caja.innerHTML = '<p class="ayuda">Todavía no tienes salas. Crea la primera arriba.</p>';
      return;
    }
    caja.innerHTML = `
      <div class="tabla-scroll"><table class="tabla">
        <thead><tr><th>Sala</th><th>Modo</th><th>Cartón</th><th>Partidas</th>
          <th>Botes</th><th>Has ganado</th><th></th></tr></thead>
        <tbody>${res.salas.map((s) => `
          <tr><td><strong>${s.nombre}</strong></td><td>${nombreModo(s.modo)}</td>
          <td>${s.precio_texto}</td><td>${g.partidas}</td><td>${g.botes_texto}</td>
          <td><strong>${g.anfitrion_texto}</strong></td>
          <td><button class="boton boton--fantasma boton--mini"
                data-cerrar="${s.id}">Cerrar</button></td></tr>`).join("")}
        </tbody></table></div>
      <p class="ayuda">Ganas el ${g.comision_pct}% del bote de cada partida de tus salas.
         Hasta ahora: <strong>${g.anfitrion_texto}</strong> de ${g.botes_texto} en botes.</p>`;
    caja.querySelectorAll("[data-cerrar]").forEach((b) =>
      (b.onclick = async () => {
        if (!confirm("¿Cerrar esta sala? No se podrá jugar más en ella.")) return;
        try {
          await post("/api/sala/cerrar", { sala: b.dataset.cerrar });
          avisar("Sala cerrada.", "bien");
          cargarMisSalas();
          cargarSalas();
        } catch (err) { avisar(err.message, "error"); }
      }));
  } catch (err) { /* sin sesión */ }
}

/* --- juego --- */

async function refrescarPartida() {
  try {
    const p = await get("/api/partida");
    $("#estado-partida").textContent =
      p.estado === "vendiendo" ? "Vendiendo cartones"
      : p.estado === "jugando" ? "En juego" : "Terminada";
    $("#precio-carton").textContent = "Cartón " + formatear(p.precio_carton);
    $("#contador-bolas").textContent = p.bolas_sacadas.length + " bolas sacadas";
    pintarBolas(p.bolas_sacadas);
    pintarOponentes(p.a_cuanto_estan);
    const mio = (p.a_cuanto_estan || []).find(
      (f) => f.jugador === (localStorage.getItem("bp777_correo") || ""));
    refrescarCercania(mio ? mio.faltan : null);
    pintarCuentaAtras(p.fecha_partida);
    const botonBola = $("#btn-bola");
    botonBola.disabled = !token || p.estado === "terminada";
    if (p.ganador) $("#estado-partida").textContent = "Ganó " + p.ganador;
  } catch (err) {
    $("#estado-partida").textContent = "Sin conexión";
  }
}

function pintarBolas(bolas) {
  const caja = $("#bolas-sacadas");
  caja.innerHTML = "";
  bolas.slice(-14).forEach((n) => {
    const s = document.createElement("span");
    s.textContent = n;
    caja.appendChild(s);
  });
  if (bolas.length) {
    const ultima = $("#ultima-bola");
    ultima.textContent = bolas[bolas.length - 1];
    ultima.classList.remove("bola--nueva");
    void ultima.offsetWidth;
    ultima.classList.add("bola--nueva");
  }
}

async function refrescarSaldo() {
  if (!token) { $("#saldo").textContent = "Bs 0,00"; return; }
  try {
    const s = await get("/api/saldo");
    $("#saldo").textContent = s.saldo_texto;
  } catch (err) { /* sin sesión válida */ }
}

async function refrescarHistorial() {
  if (!token) { $("#historial").innerHTML = '<li class="vacio">Sin movimientos.</li>'; return; }
  try {
    const h = await get("/api/historial");
    const lista = $("#historial");
    if (!h.movimientos.length) { lista.innerHTML = '<li class="vacio">Sin movimientos.</li>'; return; }
    lista.innerHTML = "";
    h.movimientos.slice().reverse().forEach((m) => {
      const li = document.createElement("li");
      const signo = m.centimos > 0 ? "mas" : "menos";
      li.innerHTML = `<span>${m.tipo}</span>
        <span class="${signo}">${m.centimos > 0 ? "+" : ""}${formatear(m.centimos)}</span>`;
      lista.appendChild(li);
    });
  } catch (err) { /* nada */ }
}

function formatear(centimos) {
  const negativo = centimos < 0;
  const n = Math.abs(centimos);
  const entero = Math.floor(n / 100).toLocaleString("es-VE");
  const resto = String(n % 100).padStart(2, "0");
  return (negativo ? "-" : "") + "Bs " + entero + "," + resto;
}

function refrescarTodo() {
  refrescarPartida();
  refrescarSaldo();
  refrescarHistorial();
  refrescarRetiros();
  refrescarDepositos();
  cargarMisSalas();
}

/* --- acciones --- */

function conectarPortada() {
  const entrar = $("#portada-entrar");
  const crear = $("#portada-crear");
  const seguir = $("#portada-seguir");
  if (entrar) entrar.onclick = () => abrirAcceso("entrar");
  if (crear) crear.onclick = () => abrirAcceso("registrar");
  if (seguir) seguir.onclick = () => {
    const jugar = $("#jugar");
    if (jugar) jugar.scrollIntoView({ behavior: "smooth" });
  };
}

function conectarBotones() {
  $("#btn-recargar").onclick = () => {
    if (!token) return abrirAcceso("entrar");
    abrirDeposito();
  };

  $("#btn-carton").onclick = async () => {
    if (!token) return abrirAcceso("entrar");
    const cantidad = parseInt($("#cuantos-cartones")?.value || "1", 10) || 1;
    try {
      const res = await post("/api/carton", { sala: salaActual, cantidad });
      carton = res;
      misCartones = res.cartones || [res];
      pintarCarton("#carton-jugador", res.numeros, []);
      $("#btn-bingo").disabled = false;
      const cuantos = res.cantidad || 1;
      avisar(cuantos > 1
        ? `${cuantos} cartones por ${res.precio_total_texto}`
        : "Cartón comprado por " + res.precio_texto, "bien");
      refrescarSaldo();
      refrescarHistorial();
      refrescarPartida();
    } catch (err) { avisar(err.message, "error"); }
  };

  $("#automarcar").onchange = (e) => {
    automarcar = e.target.checked;
    if (automarcar && carton) {
      // Marca de golpe todas las bolas ya sacadas.
      get("/api/partida").then((p) => marcarEnCarton(p.bolas_sacadas)).catch(() => {});
    }
  };

  $("#btn-bola").onclick = async () => {
    try {
      const res = await post("/api/bola", { sala: salaActual });
      pintarBolas(res.bolas);
      $("#contador-bolas").textContent = res.bolas.length + " bolas sacadas";
      if (carton && automarcar) marcarEnCarton(res.bolas);
      refrescarPartida();
    } catch (err) { avisar(err.message, "error"); }
  };

  $("#btn-retirar").onclick = async () => {
    if (!token) return abrirAcceso("entrar");
    const importe = $("#retiro-importe").value.trim();
    const metodo = $("#retiro-metodo").value;
    const detalles = $("#retiro-detalles").value.trim();
    if (!importe) return avisar("Escribe el importe a retirar.", "error");
    if (detalles.length < 5) return avisar("Escribe los datos para el pago.", "error");
    try {
      const res = await post("/api/retiro", { importe, metodo, detalles });
      avisar("Retiro pedido. Saldo: " + res.saldo_texto, "bien");
      $("#retiro-importe").value = "";
      $("#retiro-detalles").value = "";
      refrescarSaldo();
      refrescarHistorial();
      refrescarRetiros();
  refrescarDepositos();
    } catch (err) { avisar(err.message, "error"); }
  };

  $("#btn-bingo").onclick = async () => {
    if (!carton) return;
    try {
      const res = await post("/api/bingo", { carton: carton.carton, sala: salaActual });
      avisar(`¡BINGO! ${res.nombre_puesto || "Ganaste"}: ${res.premio_texto}`, "bien");
      lanzarConfeti();
      carton = null;
      misCartones = [];
      $("#btn-bingo").disabled = true;
      $("#btn-bingo").classList.remove("bingo--cerca");
      refrescarSaldo();
      refrescarHistorial();
      refrescarPartida();
      pintarEvento(salaActual);
    } catch (err) { avisar(err.message, "error"); }
  };
}

function marcarEnCarton(bolas) {
  const marcados = [];
  const numeros = carton.numeros;
  const sacadas = new Set(bolas);
  for (let f = 0; f < 5; f++) {
    for (let c = 0; c < 5; c++) {
      if (f === 2 && c === 2) continue;
      if (sacadas.has(numeros[f][c])) marcados.push([f, c]);
    }
  }
  pintarCarton("#carton-jugador", numeros, marcados);
}

/* --- transparencia: a cuánto están los demás --- */

function iniciales(correo) {
  const nombre = (correo || "?").split("@")[0];
  return nombre.slice(0, 2).toUpperCase();
}

function pintarOponentes(filas) {
  const caja = $("#oponentes");
  if (!caja) return;
  if (!filas || !filas.length) {
    caja.innerHTML = '<p class="vacio">Todavía no hay jugadores.</p>';
    return;
  }
  caja.innerHTML = "";
  filas.forEach((f) => {
    const yo = f.jugador === (localStorage.getItem("bp777_correo") || "");
    const clase = ["oponente"];
    if (yo) clase.push("oponente--yo");
    // Cerca de cantar: 1 o 2 fichas. Se resalta en verde; a 0, en rojo.
    if (f.faltan === 0) clase.push("oponente--gana");
    else if (f.faltan <= 2) clase.push("oponente--cerca");
    const texto = f.faltan === 0 ? "¡BINGO!"
      : `Faltan ${f.faltan} ${f.faltan === 1 ? "ficha" : "fichas"}`;
    caja.insertAdjacentHTML("beforeend", `
      <div class="${clase.join(" ")}">
        <div class="oponente__avatar">${iniciales(f.jugador)}</div>
        <div class="oponente__datos">
          <div class="oponente__nombre">${yo ? "Tú" : f.jugador}</div>
          <div class="oponente__cartones">${f.cartones} cartón${f.cartones === 1 ? "" : "es"}</div>
        </div>
        <span class="oponente__faltan">${texto}</span>
      </div>`);
  });
}

/* --- cuenta atrás de la partida --- */

function pintarCuentaAtras(fecha) {
  const caja = $("#cuenta-atras");
  if (!caja) return;
  clearInterval(cuentaAtras);
  // La sala guarda la fecha como texto libre ("hoy 8 pm") o como marca de
  // tiempo. Solo se cuenta atrás cuando es un número que podemos restar.
  const marca = Number(fecha);
  if (!fecha || !Number.isFinite(marca) || marca <= 0) {
    caja.hidden = true;
    return;
  }
  caja.hidden = false;
  const refrescar = () => {
    const segundos = Math.max(0, Math.round(marca - Date.now() / 1000));
    if (segundos <= 0) {
      caja.textContent = "¡Ya empieza!";
      caja.classList.add("cuenta-atras--ya");
      clearInterval(cuentaAtras);
      return;
    }
    const m = String(Math.floor(segundos / 60)).padStart(2, "0");
    const s = String(segundos % 60).padStart(2, "0");
    caja.textContent = `Empieza en ${m}:${s}`;
    caja.classList.remove("cuenta-atras--ya");
  };
  refrescar();
  cuentaAtras = setInterval(refrescar, 1000);
}

/* --- confeti de victoria --- */

function lanzarConfeti() {
  const caja = document.createElement("div");
  caja.className = "confeti";
  const colores = ["#ff6b00", "#ffd700", "#7b2cbf", "#00c853", "#ffffff"];
  for (let i = 0; i < 90; i++) {
    const trozo = document.createElement("span");
    trozo.style.left = Math.random() * 100 + "%";
    trozo.style.background = colores[i % colores.length];
    trozo.style.animationDelay = Math.random() * 0.8 + "s";
    caja.appendChild(trozo);
  }
  document.body.appendChild(caja);
  setTimeout(() => caja.remove(), 4200);
}

function refrescarCercania(faltanMio) {
  const boton = $("#btn-bingo");
  if (!boton) return;
  boton.classList.toggle("bingo--cerca", faltanMio === 1 || faltanMio === 2);
}

/* --- retiros --- */

let configRetiro = null;

async function cargarConfigRetiro() {
  try {
    configRetiro = await get("/api/config");
    preguntas = configRetiro.preguntas || [];
    const sel = $("#retiro-metodo");
    sel.innerHTML = "";
    configRetiro.metodos.forEach((m) => {
      const o = document.createElement("option");
      o.value = m;
      o.textContent = m.replace("_", " ");
      sel.appendChild(o);
    });
    $("#retiro-ayuda").textContent =
      "Mínimo " + configRetiro.retiro_minimo_texto +
      " · Tope diario " + configRetiro.retiro_tope_texto;
  } catch (err) { /* sin config no pasa nada */ }
}

async function refrescarRetiros() {
  const lista = $("#lista-retiros");
  if (!token) { lista.innerHTML = '<li class="vacio">Entra para ver tus retiros.</li>'; return; }
  try {
    const r = await get("/api/retiros");
    if (!r.retiros.length) {
      lista.innerHTML = '<li class="vacio">Todavía no has pedido ningún retiro.</li>';
      return;
    }
    lista.innerHTML = "";
    r.retiros.forEach((x) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="importe">${x.importe_texto}</span>
        <span>${x.metodo.replace("_", " ")}</span>
        <span class="retiro-estado retiro-estado--${x.estado}">${x.estado}</span>`;
      lista.appendChild(li);
    });
  } catch (err) { /* nada */ }
}

/* --- arranque --- */

// La sesión se valida contra el servidor, no contra lo guardado en el navegador.
// Así, si el token ya no vale (o es de otra cuenta), el sitio no se queda pegado
// en modo administrador: el servidor manda.
async function comprobarSesion() {
  if (!token) { esAdmin = false; pintarSesion(); return; }
  try {
    const s = await get("/api/sesion");
    esAdmin = !!s.admin;
    localStorage.setItem("bp777_correo", s.correo);
    localStorage.setItem("bp777_admin", s.admin ? "1" : "0");
  } catch (err) {
    // El token caducó o no vale: se limpia y se sigue como visitante.
    localStorage.removeItem(CLAVE_TOKEN);
    localStorage.removeItem("bp777_correo");
    localStorage.removeItem("bp777_admin");
    token = "";
    esAdmin = false;
  }
  pintarSesion();
}

// Si el navegador revive la página desde su caché (botón atrás), se comprueba
// otra vez la sesión: no puede reaparecer un panel que ya no toca.
window.addEventListener("pageshow", (e) => {
  if (e.persisted) comprobarSesion();
});
window.addEventListener("focus", () => { if (token) comprobarSesion(); });

pintarCartonDemo();
pintarSesion();
conectarBotones();
conectarPortada();
cargarConfigRetiro();
cargarSalas();
const formSala = $("#form-sala");
if (formSala) {
  formSala.onsubmit = async (e) => {
    e.preventDefault();
    if (!token) return abrirAcceso("entrar");
    const d = Object.fromEntries(new FormData(e.target));
    try {
      const res = await post("/api/sala/crear", {
        nombre: d.nombre, modo: d.modo, precio: d.precio, publica: d.publica === "si",
      });
      avisar(res.mensaje, "bien");
      formSala.reset();
      cargarSalas();
      cargarMisSalas();
    } catch (err) { avisar(err.message, "error"); }
  };
}
comprobarSesion().then(refrescarTodo);
setInterval(refrescarPartida, 5000);
