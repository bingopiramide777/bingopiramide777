/* Bingo Pirámide 777 — interfaz. Sin dependencias: JavaScript a pelo. */

const $ = (sel) => document.querySelector(sel);
const CLAVE_TOKEN = "bp777_token";

let token = localStorage.getItem(CLAVE_TOKEN) || "";
let carton = null;

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
  if (token) {
    const correo = document.createElement("span");
    correo.textContent = localStorage.getItem("bp777_correo") || "";
    correo.style.color = "var(--gris)";
    caja.append(correo);
    if (localStorage.getItem("bp777_admin") === "1") {
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
    salir.onclick = async () => {
      try { await post("/api/salir"); } catch (e) { /* da igual */ }
      localStorage.removeItem(CLAVE_TOKEN);
      localStorage.removeItem("bp777_correo");
      localStorage.removeItem("bp777_admin");
      location.reload();
    };
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
}

/* --- acciones --- */

function conectarBotones() {
  $("#btn-recargar").onclick = async () => {
    if (!token) return abrirAcceso("entrar");
    const importe = $("#importe").value.trim();
    if (!importe) return avisar("Escribe un importe.", "error");
    try {
      const res = await post("/api/recargar", { importe });
      avisar("Recarga hecha. Saldo: " + res.saldo_texto, "bien");
      $("#importe").value = "";
      refrescarSaldo();
      refrescarHistorial();
    } catch (err) { avisar(err.message, "error"); }
  };

  $("#btn-carton").onclick = async () => {
    if (!token) return abrirAcceso("entrar");
    try {
      const res = await post("/api/carton");
      carton = res;
      pintarCarton("#carton-jugador", res.numeros, []);
      $("#btn-bingo").disabled = false;
      avisar("Cartón comprado por " + res.precio_texto, "bien");
      refrescarSaldo();
      refrescarHistorial();
      refrescarPartida();
    } catch (err) { avisar(err.message, "error"); }
  };

  $("#btn-bola").onclick = async () => {
    try {
      const res = await post("/api/bola");
      pintarBolas(res.bolas);
      $("#contador-bolas").textContent = res.bolas.length + " bolas sacadas";
      if (carton) marcarEnCarton(res.bolas);
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
    } catch (err) { avisar(err.message, "error"); }
  };

  $("#btn-bingo").onclick = async () => {
    if (!carton) return;
    try {
      const res = await post("/api/bingo", { carton: carton.carton });
      avisar("¡BINGO! Has ganado " + res.premio_texto, "bien");
      refrescarSaldo();
      refrescarHistorial();
      refrescarPartida();
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

pintarCartonDemo();
pintarSesion();
conectarBotones();
cargarConfigRetiro();
refrescarTodo();
setInterval(refrescarPartida, 5000);
