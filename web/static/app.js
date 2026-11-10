/* Bingo Pirámide 777 — interfaz. Sin dependencias: JavaScript a pelo. */

const $ = (sel) => document.querySelector(sel);
const CLAVE_TOKEN = "bp777_token";

let token = localStorage.getItem(CLAVE_TOKEN) || "";
let esAdmin = false;
let carton = null;
let misCartones = [];          // todos los cartones comprados en la partida
let automarcar = false;        // marca solo las bolas que salgan
let cuentaAtras = null;        // temporizador de la cuenta atrás de la partida

/* --- país y moneda --- */
// La app sirve a varios países. El país activo decide la moneda que se muestra
// y el método de cobro. Se recuerda la elección y, si no hay, la detecta el
// servidor por el idioma o por IP.
const CLAVE_PAIS = "bp777_pais";
let paisActual = localStorage.getItem(CLAVE_PAIS) || "";
let paisInfo = null;           // { code, name, currency, currencySymbol, locale, flag }
let catalogoPaises = [];       // todos los países soportados

/* --- idioma --- */
// El idioma va aparte del país: el país decide la moneda y el cobro; el idioma,
// los textos. Así un jugador chino en Estados Unidos lee la mesa en chino y paga
// en dólares. Las funciones t() y el selector viven en i18n.js.

function simboloMoneda() {
  return (paisInfo && paisInfo.currencySymbol) || "Bs";
}

function localeMoneda() {
  return (paisInfo && paisInfo.locale) || "es-VE";
}

/* Nombre de la moneda para los textos. Siempre el dólar. */
function nombreMoneda() {
  return (paisInfo && paisInfo.currencyName) || "dólares";
}

/* --- peticiones --- */

async function pedir(ruta, opciones = {}) {
  const cabeceras = { "Content-Type": "application/json" };
  if (token) cabeceras["Authorization"] = "Bearer " + token;
  if (paisActual) cabeceras["X-Pais"] = paisActual;
  if (idiomaElegido()) cabeceras["X-Idioma"] = idiomaElegido();
  const respuesta = await fetch(ruta, { ...opciones, headers: cabeceras });
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) throw new Error(datos.error || t("aviso.algo_mal"));
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
        celda.textContent = t("mesa.libre");
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
      panel.textContent = t("sesion.panel");
      caja.appendChild(panel);
    }
    const perfil = document.createElement("button");
    perfil.className = "boton boton--fantasma";
    perfil.style.padding = ".4rem 1rem";
    perfil.innerHTML = `<span id="mini-avatar" class="mini-avatar">${iniciales(localStorage.getItem("bp777_correo") || "")}</span> ${t("perfil.boton")}`;
    perfil.onclick = () => abrirPerfil();
    caja.appendChild(perfil);
    const salir = document.createElement("button");
    salir.className = "boton boton--fantasma";
    salir.textContent = t("sesion.salir");
    salir.style.padding = ".4rem 1rem";
    salir.onclick = () => cerrarSesion();
    caja.append(salir);
  } else {
    const entrar = document.createElement("button");
    entrar.className = "boton boton--principal";
    entrar.style.padding = ".45rem 1.1rem";
    entrar.textContent = t("sesion.entrar");
    entrar.onclick = () => abrirAcceso("entrar");
    caja.appendChild(entrar);
  }
  pintarMiniAvatar();
}

/* Borra la sesión de este dispositivo. El panel de administración es una página
   aparte: nunca se recuerda aquí, así que este cierre no afecta a nadie más. */
function cerrarSesion() {
  try { post("/api/salir"); } catch (e) { /* da igual */ }
  localStorage.removeItem(CLAVE_TOKEN);
  localStorage.removeItem("bp777_correo");
  localStorage.removeItem("bp777_admin");
  localStorage.removeItem("bp777_foto");
  token = "";
  location.reload();
}

/* --- perfil: foto del jugador --- */

function pintarMiniAvatar() {
  const caja = $("#mini-avatar");
  if (!caja) return;
  const foto = localStorage.getItem("bp777_foto") || "";
  caja.innerHTML = foto
    ? `<img src="${foto}" alt="" onerror="this.parentNode.textContent='${iniciales(localStorage.getItem("bp777_correo") || "")}'">`
    : iniciales(localStorage.getItem("bp777_correo") || "");
}

function abrirPerfil() {
  const foto = localStorage.getItem("bp777_foto") || "";
  $("#dialogo-contenido").innerHTML = `
    <h2>${t("perfil.titulo")}</h2>
    <p style="color:var(--gris);font-size:.9rem">${t("perfil.ayuda")}</p>
    <div class="perfil-previa" id="perfil-previa">
      ${foto ? `<img src="${foto}" alt="">` : `<span class="perfil-previa__vacia">${iniciales(localStorage.getItem("bp777_correo") || "")}</span>`}
    </div>
    <input type="file" id="perfil-archivo" accept="image/png,image/jpeg,image/webp,image/gif">
    <div style="display:flex;gap:.6rem;margin-top:.8rem">
      <button class="boton boton--principal boton--alto" id="perfil-guardar" type="button">${t("perfil.guardar")}</button>
      <button class="boton boton--fantasma boton--alto" id="perfil-quitar" type="button">${t("perfil.quitar")}</button>
    </div>`;
  $("#dialogo").hidden = false;
  $("#dialogo-cerrar").onclick = () => ($("#dialogo").hidden = true);

  let dataUrl = foto;
  $("#perfil-archivo").onchange = (e) => {
    const archivo = e.target.files[0];
    if (!archivo) return;
    const lector = new FileReader();
    lector.onload = () => {
      // Se reduce la imagen a 256×256 para que pese poco y quepa en la base.
      const img = new Image();
      img.onload = () => {
        const lado = 256;
        const lienzo = document.createElement("canvas");
        lienzo.width = lado; lienzo.height = lado;
        const ctx = lienzo.getContext("2d");
        const min = Math.min(img.width, img.height);
        ctx.drawImage(img, (img.width - min) / 2, (img.height - min) / 2, min, min, 0, 0, lado, lado);
        dataUrl = lienzo.toDataURL("image/jpeg", 0.85);
        $("#perfil-previa").innerHTML = `<img src="${dataUrl}" alt="">`;
      };
      img.onerror = () => avisar(t("perfil.no_imagen"), "error");
      img.src = lector.result;
    };
    lector.readAsDataURL(archivo);
  };
  $("#perfil-guardar").onclick = async () => {
    try {
      const res = await post("/api/foto", { foto: dataUrl });
      if (res.foto_url) localStorage.setItem("bp777_foto", res.foto_url + "&t=" + Date.now());
      else localStorage.removeItem("bp777_foto");
      pintarMiniAvatar();
      $("#dialogo").hidden = true;
      avisar(res.mensaje || t("perfil.guardada"), "bien");
      refrescarPartida();
    } catch (err) { avisar(err.message, "error"); }
  };
  $("#perfil-quitar").onclick = async () => {
    try {
      const res = await post("/api/foto", { foto: "" });
      localStorage.removeItem("bp777_foto");
      pintarMiniAvatar();
      $("#dialogo").hidden = true;
      avisar(res.mensaje || t("perfil.quitada"), "bien");
      refrescarPartida();
    } catch (err) { avisar(err.message, "error"); }
  };
}

/* --- diálogo de acceso --- */

let preguntas = [];

function abrirAcceso(modo) {
  const cabeceras = {
    entrar: [t("acceso.entrar_t"), t("acceso.entrar_d")],
    registrar: [t("acceso.crear_t"), t("acceso.crear_d")],
    recuperar: [t("acceso.recuperar_t"), t("acceso.recuperar_d")],
  };
  const [titulo, ayuda] = cabeceras[modo] || cabeceras.entrar;

  const campos = {
    entrar: `
      <label>${t("acceso.correo")}<input type="email" name="correo" required placeholder="${t("acceso.correo_ph")}" autocomplete="email"></label>
      <label>${t("acceso.clave")}<input type="password" name="clave" required placeholder="••••••••" autocomplete="current-password"></label>
      <button class="boton boton--principal boton--alto" type="submit">${t("acceso.entrar_t")}</button>`,
    registrar: `
      <label>${t("acceso.nombre")}<input type="text" name="nombre" placeholder="${t("acceso.nombre_ph")}"></label>
      <label>${t("acceso.correo")}<input type="email" name="correo" required placeholder="${t("acceso.correo_ph")}" autocomplete="email"></label>
      <label>${t("acceso.clave")}<input type="password" name="clave" required minlength="8" placeholder="••••••••" autocomplete="new-password"></label>
      <label>${t("acceso.codigo_amigo")}<input type="text" name="codigo_amigo" maxlength="10" placeholder="${t("acceso.codigo_amigo_ph")}" style="text-transform:uppercase"></label>
      <label>${t("acceso.pregunta")}
        <select name="pregunta"><option value="">${t("acceso.sin_pregunta")}</option></select>
      </label>
      <label>${t("acceso.respuesta")}<input type="text" name="respuesta" placeholder="${t("acceso.respuesta_ph")}"></label>
      <button class="boton boton--principal boton--alto" type="submit">${t("acceso.crear_t")}</button>`,
    recuperar: `
      <label>${t("acceso.correo")}<input type="email" name="correo" required placeholder="${t("acceso.correo_ph")}" autocomplete="email"></label>
      <button class="boton boton--principal" type="submit" id="btn-enviar-codigo">${t("acceso.enviar_codigo")}</button>
      <div id="paso-codigo" hidden>
        <label>${t("acceso.codigo")}<input type="text" name="codigo" inputmode="numeric" maxlength="6" placeholder="000000"></label>
        <label>${t("acceso.clave_nueva")}<input type="password" name="clave" minlength="8" placeholder="••••••••" autocomplete="new-password"></label>
        <button class="boton boton--principal" type="submit" id="btn-cambiar-codigo">${t("acceso.cambiar_clave")}</button>
      </div>
      <p class="ayuda">${t("acceso.usar_pregunta")}
        <button type="button" class="enlace" id="usar-pregunta">${t("acceso.usar_pregunta_b")}</button></p>
      <div id="paso-pregunta" hidden>
        <label>${t("acceso.pregunta")}<input type="text" name="pregunta_mostrada" readonly></label>
        <label>${t("acceso.respuesta")}<input type="text" name="respuesta" placeholder="${t("acceso.respuesta_ph")}"></label>
        <label>${t("acceso.clave_nueva")}<input type="password" name="clave2" minlength="8" placeholder="••••••••" autocomplete="new-password"></label>
        <button class="boton boton--principal" type="submit" id="btn-cambiar-pregunta">${t("acceso.cambiar_clave")}</button>
      </div>`,
  };

  $("#dialogo-contenido").innerHTML = `
    <h2>${titulo}</h2>
    <p style="color:var(--gris);font-size:.9rem">${ayuda}</p>
    <form id="form-acceso">${campos[modo]}</form>
    <p class="dialogo__cambio">
      ${modo === "entrar" ? `${t("acceso.no_cuenta")} <button id="ir-registrar">${t("acceso.creala")}</button> · <button id="ir-recuperar">${t("acceso.olvide")}</button>`
        : `<button id="ir-entrar">${t("acceso.volver")}</button>`}
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
      if (!correoDe()) return avisar(t("acceso.falta_correo"), "error");
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
      if (!correoDe()) return avisar(t("acceso.falta_correo2"), "error");
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
        avisar(t("acceso.bienvenido"), "bien");
        pintarSesion();
        refrescarTodo();
        refrescarRetiros();
  refrescarDepositos();
        if (salaInvitada) {
          const id = salaInvitada;
          salaInvitada = "";
          await entrarASala(id);
        }
      } else {
        const res = await post("/api/registro", datos);
        if (res.verificacion_requerida) {
          // Hay correo configurado: hay que confirmar el código antes de entrar.
          avisar(res.mensaje, "bien");
          abrirVerificacion(datos.correo);
        } else {
          avisar(t("acceso.cuenta_creada"), "bien");
          abrirAcceso("entrar");
        }
      }
    } catch (err) {
      avisar(err.message, "error");
    }
  };
}

/* --- confirmar el correo al crear la cuenta --- */

function abrirVerificacion(correo) {
  $("#dialogo-contenido").innerHTML = `
    <h2>${t("acceso.confirmar_t")}</h2>
    <p style="color:var(--gris);font-size:.9rem">${t("acceso.confirmar_d", { correo })}</p>
    <form id="form-verificar">
      <label>${t("acceso.codigo")}
        <input type="text" name="codigo" inputmode="numeric" maxlength="6" placeholder="000000" required>
      </label>
      <button class="boton boton--principal" type="submit">${t("acceso.confirmar")}</button>
    </form>
    <p class="dialogo__cambio">
      <button type="button" id="verificar-reenviar">${t("acceso.reenviar")}</button> ·
      <button type="button" id="verificar-entrar">${t("acceso.ya_confirme")}</button>
    </p>`;
  $("#dialogo").hidden = false;
  $("#dialogo-cerrar").onclick = () => ($("#dialogo").hidden = true);
  $("#form-verificar").onsubmit = async (e) => {
    e.preventDefault();
    const codigo = e.target.querySelector("[name=codigo]").value.trim();
    try {
      const res = await post("/api/verificar", { correo, codigo });
      $("#dialogo").hidden = true;
      avisar(res.mensaje, "bien");
      abrirAcceso("entrar");
    } catch (err) { avisar(err.message, "error"); }
  };
  $("#verificar-reenviar").onclick = async () => {
    try {
      const res = await post("/api/verificar/reenviar", { correo });
      avisar(res.mensaje, res.enviado ? "bien" : "");
    } catch (err) { avisar(err.message, "error"); }
  };
  $("#verificar-entrar").onclick = () => { $("#dialogo").hidden = true; abrirAcceso("entrar"); };
}

/* --- depósitos --- */

async function refrescarDepositos() {
  const caja = $("#mis-depositos");
  if (!caja) return;
  if (!token) { caja.innerHTML = ""; return; }
  try {
    const res = await get("/api/depositos");
    if (!res.depositos.length) {
      caja.innerHTML = `<p class="ayuda">${t("deposito.sin_pagos")}</p>`;
      return;
    }
    caja.innerHTML = `
      <h3 class="tabla__titulo">${t("deposito.mis_pagos")}</h3>
      <div class="tabla-scroll"><table class="tabla">
        <thead><tr><th>${t("deposito.tabla_monto")}</th><th>${t("deposito.tabla_referencia")}</th><th>${t("deposito.tabla_dia")}</th><th>${t("deposito.tabla_estado")}</th></tr></thead>
        <tbody>${res.depositos.map((d) => `
          <tr><td>${d.importe_texto}</td><td>${d.referencia}</td><td>${d.dia}</td>
          <td><span class="etiqueta etiqueta--${d.estado}">${
            { pendiente: t("deposito.estado_pendiente"), acreditado: t("deposito.estado_acreditado"),
              rechazado: t("deposito.estado_rechazado") }[d.estado] || d.estado}</span></td></tr>`).join("")}
        </tbody></table></div>`;
  } catch (err) { /* sin sesión: no se muestra nada */ }
}

/* Recargar saldo ya no se hace a mano: el jugador declara un pago (PayPal o
   USDT) y la administración lo revisa y lo acredita. */
function abrirDeposito() {
  const sim = simboloMoneda();
  const hoy = new Date().toISOString().slice(0, 10);
  const metodos = (configRetiro && configRetiro.metodos_pago) || [];
  const opciones = metodos.length ? metodos : [
    { id: "paypal", name: "PayPal", platformAccount: [] },
    { id: "cripto", name: "USDT (cripto)", platformAccount: [] },
  ];
  // El bloque de a dónde pagar cambia según el método elegido.
  const bloqueDe = (m) => {
    const cuentas = (m && m.platformAccount) || [];
    if (!cuentas.length) return "";
    return `<div class="cuenta-pago">
      <p class="cuenta-pago__titulo">${t("deposito.paga_a_metodo", { metodo: m.name })}</p>
      ${cuentas.map((c) => `<p class="cuenta-pago__linea"><span>${c.label}</span>
        <strong class="mono">${c.value}</strong>
        <button type="button" class="boton boton--fantasma boton--mini"
                data-copiar="${c.value}">${t("deposito.copiar")}</button></p>`).join("")}
    </div>`;
  };
  $("#dialogo-contenido").innerHTML = `
    <h2>${t("deposito.titulo")}</h2>
    <div id="deposito-cuenta">${bloqueDe(opciones[0])}</div>
    <p style="color:var(--gris);font-size:.9rem">
      ${t("deposito.instrucciones", { minimo: configRetiro ? configRetiro.deposito_minimo_texto : "" })}</p>
    <form id="form-deposito">
      <label>${t("deposito.metodo")}
        <select name="metodo">
          ${opciones.map((m) => `<option value="${m.id}">${m.name}</option>`).join("")}
        </select>
      </label>
      <label>${t("deposito.monto", { moneda: sim })}
        <input type="text" name="importe" inputmode="decimal" placeholder="${sim} 100,00" required>
      </label>
      <label>${t("deposito.referencia")}
        <input type="text" name="referencia" placeholder="${t("deposito.referencia_ph")}" required>
      </label>
      <label>${t("deposito.dia")}
        <input type="text" name="dia" value="${hoy}" placeholder="AAAA-MM-DD">
      </label>
      <button class="boton boton--principal boton--alto" type="submit">${t("deposito.anotar")}</button>
    </form>`;
  $("#dialogo").hidden = false;
  $("#dialogo-cerrar").onclick = () => ($("#dialogo").hidden = true);
  const conectarCopiar = () =>
    $("#dialogo-contenido").querySelectorAll("[data-copiar]").forEach((b) =>
      (b.onclick = async () => {
        try { await navigator.clipboard.writeText(b.dataset.copiar); avisar(t("deposito.copiado"), "bien"); }
        catch (err) { avisar(t("deposito.copiar_manual"), "error"); }
      }));
  conectarCopiar();
  const sel = $("#form-deposito select[name=metodo]");
  sel.onchange = () => {
    const m = opciones.find((x) => x.id === sel.value) || opciones[0];
    $("#deposito-cuenta").innerHTML = bloqueDe(m);
    conectarCopiar();
  };
  $("#form-deposito").onsubmit = async (e) => {
    e.preventDefault();
    const datos = Object.fromEntries(new FormData(e.target));
    datos.pais = paisActual;
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
let topeSalaActual = 0;
let salaInvitada = "";

async function cargarSalas() {
  const caja = $("#lista-salas");
  if (!caja) return;
  try {
    const res = await get("/api/salas");
    salasDisponibles = res.salas;
    caja.innerHTML = salasDisponibles.map((s) => s.es_evento
      ? `<button class="sala-tarjeta sala-tarjeta--evento ${s.id === salaActual ? "sala-tarjeta--activa" : ""}"
                 data-sala="${s.id}">
           <span class="sala-tarjeta__etiqueta">${t("salas.evento_etiqueta")}</span>
           <div class="sala-tarjeta__nombre">${s.nombre}</div>
           <div class="sala-tarjeta__modo">${nombreModo(s.modo)}</div>
           <div class="sala-tarjeta__precio">${t("mesa.carton_precio", { precio: s.precio_texto })}</div>
           <div class="sala-tarjeta__dueno">${t("salas.evento_pie")}</div>
         </button>`
      : `<button class="sala-tarjeta ${s.id === salaActual ? "sala-tarjeta--activa" : ""}"
                 data-sala="${s.id}">
           <div class="sala-tarjeta__nombre">${s.nombre}</div>
           <div class="sala-tarjeta__modo">${nombreModo(s.modo)}</div>
           <div class="sala-tarjeta__precio">${t("mesa.carton_precio", { precio: s.precio_texto })}</div>
           ${s.es_de_jugador ? `<div class="sala-tarjeta__dueno">${t("salas.de_jugador", { dueno: s.dueno })}</div>`
                             : `<div class="sala-tarjeta__dueno">${t("salas.de_casa")}</div>`}
           ${s.max_cartones > 0
             ? `<div class="sala-tarjeta__dueno">${t("salas.max_cartones", { n: s.max_cartones })}</div>`
             : ""}
         </button>`).join("");
    caja.querySelectorAll("[data-sala]").forEach((b) =>
      (b.onclick = () => entrarASala(b.dataset.sala)));
    const evento = salasDisponibles.find((s) => s.es_evento);
    pintarEvento(evento ? evento.id : "");
    // Enlace exclusivo: ?sala=<id> entra directo a esa sala, aunque sea privada
    // (las privadas no salen en el listado; el id es el secreto del enlace).
    const invitada = new URLSearchParams(location.search).get("sala");
    if (invitada) {
      if (!token) {
        // Sin sesión: se pide entrar y, al hacerlo, se entra a la sala del enlace.
        salaInvitada = invitada;
        abrirAcceso("entrar");
        return;
      }
      await entrarASala(invitada);
      return;
    }
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
        <div class="premio__puesto">${nombrePuesto(p.puesto)}</div>
        <div class="premio__importe">${p.premio_texto}</div>
        <div class="premio__pct">${t("torneo.del_bote", { pct: p.pct_texto })}</div>
      </div>`).join("");
    caja.innerHTML = `
      <div class="evento">
        <div class="evento__cabecera">
          <h3 class="evento__titulo">${e.nombre}</h3>
          <span class="evento__aforo ${e.llena ? "evento__aforo--lleno" : ""}">
            ${e.llena ? t("torneo.aforo_completo")
              : t("torneo.jugadores", { n: e.jugadores, aforo: e.aforo || "∞" })}
          </span>
        </div>
        <p class="evento__bote">${t("torneo.bote", { precio: e.precio_texto, bote: e.bote_texto })}</p>
        <div class="evento__premios">${premios || `<p class="ayuda">${t("torneo.sin_premios")}</p>`}</div>
      </div>`;
  } catch (err) { caja.innerHTML = ""; }
}

function nombrePuesto(n) {
  return t("puesto." + n) || n + "º";
}

function nombreModo(modo) {
  const clave = "modo." + modo;
  const nombre = t(clave);
  return nombre === clave ? modo : nombre;
}

async function entrarASala(id) {
  try {
    const res = await post("/api/sala/entrar", { sala: id });
    salaActual = id;
    topeSalaActual = res.partida ? (res.partida.max_cartones || 0) : 0;
    document.querySelectorAll("[data-sala]").forEach((b) =>
      b.classList.toggle("sala-tarjeta--activa", b.dataset.sala === id));
    carton = null;
    const caja = $("#carton-jugador");
    if (caja) caja.innerHTML = `<p class="vacio">${t("mesa.sin_carton")}</p>`;
    const botonBingo = $("#btn-bingo");
    if (botonBingo) botonBingo.disabled = true;
    ajustarSelectorCartones();
    refrescarPartida();
  } catch (err) { avisar(err.message, "error"); }
}

/* El selector de cartones nunca ofrece más de los que permite la sala. */
function ajustarSelectorCartones() {
  const select = $("#cuantos-cartones");
  if (!select) return;
  const sala = salasDisponibles.find((s) => s.id === salaActual);
  // Si la sala no está en el listado (enlace privado), se usa el tope que
  // devolvió el servidor al entrar.
  const tope = sala && sala.max_cartones > 0 ? Math.min(sala.max_cartones, 10)
    : (topeSalaActual > 0 ? Math.min(topeSalaActual, 10) : 10);
  select.querySelectorAll("option").forEach((o) => {
    o.disabled = parseInt(o.value, 10) > tope;
  });
  if (parseInt(select.value, 10) > tope) select.value = String(tope);
}

/* El enlace exclusivo de una sala: lleva su id para entrar directo. */
function enlaceDeSala(id) {
  return `${location.origin}${location.pathname}?sala=${encodeURIComponent(id)}`;
}

async function copiarEnlaceSala(id) {
  const enlace = enlaceDeSala(id);
  try {
    await navigator.clipboard.writeText(enlace);
    avisar(t("salas.enlace_copiado"), "bien");
  } catch (err) {
    // Sin permiso de portapapeles (o sin HTTPS): se muestra para copiar a mano.
    prompt(t("salas.copiar_manual"), enlace);
  }
}

async function cargarMisSalas() {
  const caja = $("#tabla-mis-salas");
  if (!caja) return;
  if (!token) { caja.innerHTML = `<p class="ayuda">${t("salas.entra_crear")}</p>`; return; }
  try {
    const res = await get("/api/mis-salas");
    const g = res.ganancias;
    const p = $("#ganancias-pastilla");
    if (p) p.textContent = t("salas.ganas", { monto: g.anfitrion_texto });
    if (!res.salas.length) {
      caja.innerHTML = `<p class="ayuda">${t("salas.sin_salas")}</p>`;
      return;
    }
    caja.innerHTML = `
      <div class="tabla-scroll"><table class="tabla">
        <thead><tr><th>${t("salas.tabla_sala")}</th><th>${t("salas.tabla_modo")}</th><th>${t("salas.tabla_carton")}</th><th>${t("salas.tabla_partidas")}</th>
          <th>${t("salas.tabla_botes")}</th><th>${t("salas.tabla_ganado")}</th><th></th></tr></thead>
        <tbody>${res.salas.map((s) => `
          <tr><td><strong>${s.nombre}</strong><br>
                <span class="ayuda">${s.publica ? t("salas.publica_corta") : t("salas.privada_corta")}</span></td>
          <td>${nombreModo(s.modo)}</td>
          <td>${s.precio_texto}</td><td>${g.partidas}</td><td>${g.botes_texto}</td>
          <td><strong>${g.anfitrion_texto}</strong></td>
          <td class="acciones-celda">
            <button class="boton boton--fantasma boton--mini"
                    data-enlace="${s.id}">${t("salas.copiar_enlace")}</button>
            <button class="boton boton--fantasma boton--mini"
                    data-cerrar="${s.id}">${t("salas.cerrar")}</button></td></tr>`).join("")}
        </tbody></table></div>
      <p class="ayuda">${t("salas.pie", { pct: g.comision_pct, ganado: g.anfitrion_texto, botes: g.botes_texto })}</p>`;
    caja.querySelectorAll("[data-enlace]").forEach((b) =>
      (b.onclick = () => copiarEnlaceSala(b.dataset.enlace)));
    caja.querySelectorAll("[data-cerrar]").forEach((b) =>
      (b.onclick = async () => {
        if (!confirm(t("salas.confirmar_cerrar"))) return;
        try {
          await post("/api/sala/cerrar", { sala: b.dataset.cerrar });
          avisar(t("salas.cerrada"), "bien");
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
      p.estado === "vendiendo" ? t("mesa.vendiendo")
      : p.estado === "jugando" ? t("mesa.en_juego") : t("mesa.terminada");
    $("#precio-carton").textContent = t("mesa.carton_precio", { precio: formatear(p.precio_carton) });
    $("#contador-bolas").textContent = t("mesa.bolas_sacadas", { n: p.bolas_sacadas.length });
    pintarBolas(p.bolas_sacadas);
    pintarOponentes(p.a_cuanto_estan);
    const mio = (p.a_cuanto_estan || []).find(
      (f) => f.jugador === (localStorage.getItem("bp777_correo") || ""));
    refrescarCercania(mio ? mio.faltan : null);
    pintarCuentaAtras(p.fecha_partida);
    const botonBola = $("#btn-bola");
    botonBola.disabled = !token || p.estado === "terminada";
    if (p.ganador) $("#estado-partida").textContent = t("mesa.gano", { nombre: p.ganador });
  } catch (err) {
    $("#estado-partida").textContent = t("mesa.sin_conexion");
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
  if (!token) { $("#saldo").textContent = formatear(0); return; }
  try {
    const s = await get("/api/saldo");
    $("#saldo").textContent = s.saldo_texto;
  } catch (err) { /* sin sesión válida */ }
}

async function refrescarHistorial() {
  if (!token) { $("#historial").innerHTML = `<li class="vacio">${t("mesa.sin_movimientos")}</li>`; return; }
  try {
    const h = await get("/api/historial");
    const lista = $("#historial");
    if (!h.movimientos.length) { lista.innerHTML = `<li class="vacio">${t("mesa.sin_movimientos")}</li>`; return; }
    lista.innerHTML = "";
    h.movimientos.slice().reverse().forEach((m) => {
      const li = document.createElement("li");
      const signo = m.centimos > 0 ? "mas" : "menos";
      const nombre = t("mov." + m.tipo);
      li.innerHTML = `<span>${nombre === "mov." + m.tipo ? m.tipo : nombre}</span>
        <span class="${signo}">${m.centimos > 0 ? "+" : ""}${formatear(m.centimos)}</span>`;
      lista.appendChild(li);
    });
  } catch (err) { /* nada */ }
}

function formatear(centimos) {
  const negativo = centimos < 0;
  const n = Math.abs(centimos);
  const entero = Math.floor(n / 100).toLocaleString(localeMoneda());
  const resto = String(n % 100).padStart(2, "0");
  return (negativo ? "-" : "") + simboloMoneda() + " " + entero + "," + resto;
}

function refrescarTodo() {
  refrescarPartida();
  refrescarSaldo();
  refrescarHistorial();
  refrescarRetiros();
  refrescarDepositos();
  cargarMisSalas();
  cargarReferidos();
  cargarEstadisticas();
  cargarTorneo();
}

/* --- referidos: invita y gana --- */

async function cargarReferidos() {
  const caja = $("#tabla-referidos");
  if (!caja) return;
  const codigo = $("#referidos-codigo");
  const pie = $("#referidos-pie");
  const pastilla = $("#referidos-pastilla");
  if (!token) {
    if (codigo) codigo.textContent = "—";
    if (pie) pie.textContent = t("referidos.entra");
    caja.innerHTML = "";
    return;
  }
  try {
    const r = await get("/api/referidos");
    if (codigo) codigo.textContent = r.codigo || "—";
    if (pastilla) pastilla.textContent = r.total_texto;
    if (pie) pie.textContent = t("referidos.pie", {
      pct: r.pct, invitados: r.invitados, total: r.total_texto,
    });
    if (!r.detalle.length) {
      caja.innerHTML = `<p class="ayuda">${t("referidos.sin_comisiones")}</p>`;
      return;
    }
    caja.innerHTML = `
      <div class="tabla-scroll"><table class="tabla">
        <thead><tr><th>${t("referidos.tabla_amigo")}</th><th>${t("referidos.tabla_monto")}</th></tr></thead>
        <tbody>${r.detalle.map((d) => `
          <tr><td>${d.invitado}</td><td><strong>${d.texto}</strong></td></tr>`).join("")}
        </tbody></table></div>`;
  } catch (err) { /* sin sesión */ }
}

/* --- estadísticas del jugador --- */

async function cargarEstadisticas() {
  const caja = $("#mis-stats");
  if (!caja) return;
  if (!token) {
    caja.innerHTML = `<p class="vacio">${t("stats.entra_ver")}</p>`;
    $("#tabla-ranking").innerHTML = `<p class="vacio">${t("stats.entra_ranking")}</p>`;
    return;
  }
  try {
    const e = await get("/api/estadisticas");
    const j = e.jugador;
    const netoClase = j.neto >= 0 ? "mas" : "menos";
    caja.innerHTML = `
      <div class="stat"><span class="stat__numero">${j.cartones}</span><span class="stat__texto">${t("stats.cartones")}</span></div>
      <div class="stat"><span class="stat__numero">${j.partidas}</span><span class="stat__texto">${t("stats.partidas")}</span></div>
      <div class="stat"><span class="stat__numero">${j.premios_ganados}</span><span class="stat__texto">${t("stats.premios")}</span></div>
      <div class="stat"><span class="stat__numero">${j.total_ganado_texto}</span><span class="stat__texto">${t("stats.ganado")}</span></div>
      <div class="stat"><span class="stat__numero">${j.total_apostado_texto}</span><span class="stat__texto">${t("stats.apostado")}</span></div>
      <div class="stat"><span class="stat__numero ${netoClase}">${j.neto_texto}</span><span class="stat__texto">${t("stats.neto")}</span></div>`;
    $("#estadisticas-pastilla").textContent = j.puesto
      ? t("stats.puesto", { n: j.puesto }) : t("stats.sin_premios");

    const filas = e.ranking || [];
    const tabla = $("#tabla-ranking");
    if (!filas.length) {
      tabla.innerHTML = `<p class="vacio">${t("stats.sin_ganadores")}</p>`;
      return;
    }
    tabla.innerHTML = `
      <table class="tabla">
        <thead><tr><th>#</th><th>${t("stats.tabla_jugador")}</th><th>${t("stats.tabla_premios")}</th><th>${t("stats.tabla_ganado")}</th></tr></thead>
        <tbody>${filas.map((f) => `
          <tr class="${f.correo === j.correo ? "tabla__yo" : ""}">
            <td>${f.puesto}</td><td>${f.correo}</td><td>${f.premios}</td>
            <td>${f.ganado_texto}</td>
          </tr>`).join("")}</tbody>
      </table>`;
  } catch (err) { /* sin sesión válida */ }
}

/* --- torneo del día --- */

async function cargarTorneo() {
  const caja = $("#torneo-info");
  if (!caja) return;
  try {
    const e = await get("/api/evento");
    if (!e || e.activa === false || !e.nombre) {
      caja.innerHTML = `<p class="vacio">${t("torneo.sin_torneo")}</p>`;
      $("#torneo-pastilla").textContent = "—";
      return;
    }
    const premios = (e.premios || []).map((p) => `
      <div class="premio">
        <div class="premio__puesto">${nombrePuesto(p.puesto)}</div>
        <div class="premio__importe">${p.premio_texto}</div>
        <div class="premio__pct">${t("torneo.del_bote", { pct: p.pct_texto })}</div>
      </div>`).join("");
    caja.innerHTML = `
      <div class="evento">
        <div class="evento__cabecera">
          <h3 class="evento__titulo">${e.nombre}</h3>
          <span class="evento__aforo ${e.llena ? "evento__aforo--lleno" : ""}">
            ${e.llena ? t("torneo.aforo_completo")
              : t("torneo.jugadores", { n: e.jugadores, aforo: e.aforo || "∞" })}
          </span>
        </div>
        <p class="evento__bote">${t("torneo.bote", { precio: e.precio_texto, bote: e.bote_texto })}</p>
        <div class="evento__premios">${premios || `<p class="ayuda">${t("torneo.sin_premios")}</p>`}</div>
      </div>`;
    $("#torneo-pastilla").textContent = e.llena ? t("torneo.aforo_completo") : t("torneo.plazas");
  } catch (err) {
    caja.innerHTML = `<p class="vacio">${t("torneo.sin_torneo")}</p>`;
  }
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

  const copiarCodigo = $("#btn-copiar-codigo");
  if (copiarCodigo) copiarCodigo.onclick = async () => {
    if (!token) return abrirAcceso("entrar");
    const codigo = $("#referidos-codigo").textContent.trim();
    try {
      await navigator.clipboard.writeText(codigo);
      avisar(t("referidos.codigo_copiado"), "bien");
    } catch (err) {
      // Sin permiso de portapapeles: se muestra para copiar a mano.
      prompt(t("referidos.copiar_manual"), codigo);
    }
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
        ? t("jugador.cartones_comprados", { n: cuantos, precio: res.precio_total_texto })
        : t("jugador.carton_comprado", { precio: res.precio_texto }), "bien");
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
      $("#contador-bolas").textContent = t("mesa.bolas_sacadas", { n: res.bolas.length });
      if (carton && automarcar) marcarEnCarton(res.bolas);
      refrescarPartida();
    } catch (err) { avisar(err.message, "error"); }
  };

  $("#btn-retirar").onclick = async () => {
    if (!token) return abrirAcceso("entrar");
    const importe = $("#retiro-importe").value.trim();
    const metodo = $("#retiro-metodo").value;
    const detalles = $("#retiro-detalles").value.trim();
    if (!importe) return avisar(t("retirar.falta_importe"), "error");
    if (detalles.length < 5) return avisar(t("retirar.falta_datos"), "error");
    try {
      const res = await post("/api/retiro", { importe, metodo, detalles });
      avisar(t("retirar.pedido", { saldo: res.saldo_texto }), "bien");
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
      avisar(t("jugador.bingo_premio",
        { puesto: res.nombre_puesto || t("jugador.ganaste"), premio: res.premio_texto }), "bien");
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

/* El avatar muestra la foto del jugador si la tiene; si no, sus iniciales. */
function avatarHTML(f) {
  const foto = f.foto_url
    ? `<img src="${f.foto_url}" alt="" loading="lazy"
         onerror="this.replaceWith(document.createTextNode('${iniciales(f.correo || f.jugador)}'))">`
    : iniciales(f.correo || f.jugador);
  return `<div class="oponente__avatar${f.foto_url ? " oponente__avatar--foto" : ""}">${foto}</div>`;
}

function pintarOponentes(filas) {
  const caja = $("#oponentes");
  if (!caja) return;
  if (!filas || !filas.length) {
    caja.innerHTML = `<p class="vacio">${t("mesa.sin_jugadores")}</p>`;
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
    const texto = f.faltan === 0 ? t("jugador.bingo")
      : t("jugador.faltan", { n: f.faltan, ficha: f.faltan === 1 ? t("jugador.ficha") : t("jugador.fichas") });
    const nombre = f.nombre || (f.correo || f.jugador).split("@")[0];
    caja.insertAdjacentHTML("beforeend", `
      <div class="${clase.join(" ")}">
        ${avatarHTML(f)}
        <div class="oponente__datos">
          <div class="oponente__nombre">${yo ? t("jugador.tu") : nombre}</div>
          <div class="oponente__cartones">${f.cartones === 1
            ? t("jugador.carton", { n: f.cartones })
            : t("jugador.cartones", { n: f.cartones })}</div>
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
      caja.textContent = t("cuenta.ya");
      caja.classList.add("cuenta-atras--ya");
      clearInterval(cuentaAtras);
      return;
    }
    const m = String(Math.floor(segundos / 60)).padStart(2, "0");
    const s = String(segundos % 60).padStart(2, "0");
    caja.textContent = t("cuenta.empieza", { tiempo: `${m}:${s}` });
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
      const nombre = t("metodo." + m);
      o.textContent = nombre === "metodo." + m ? m.replace("_", " ") : nombre;
      sel.appendChild(o);
    });
    $("#retiro-ayuda").textContent = t("retirar.limites", {
      minimo: configRetiro.retiro_minimo_texto,
      tope: configRetiro.retiro_tope_texto,
    });
  } catch (err) { /* sin config no pasa nada */ }
}

/* --- país y moneda --- */

async function cargarPaises() {
  try {
    const cat = await get("/api/paises");
    catalogoPaises = cat.paises || [];
    // Si el jugador no ha elegido país, se adopta el que detectó el servidor
    // (por idioma o IP); así los importes salen en la moneda correcta.
    if (!paisActual) paisActual = cat.pais_actual || cat.pais_por_defecto || "VE";
    // Si el país guardado ya no existe, se vuelve al de por defecto.
    if (!catalogoPaises.some((p) => p.code === paisActual)) {
      paisActual = cat.pais_por_defecto || "VE";
    }
    paisInfo = catalogoPaises.find((p) => p.code === paisActual) || catalogoPaises[0] || null;
    pintarSelectorPais();
  } catch (err) { /* sin catálogo se queda en dólares */ }
}

function pintarSelectorPais() {
  const caja = $("#pais-selector");
  if (!caja || !catalogoPaises.length) return;
  caja.innerHTML = `
    <select id="select-pais" aria-label="País y moneda">
      ${catalogoPaises.map((p) => `<option value="${p.code}"
        ${p.code === paisActual ? "selected" : ""}>${p.flag} ${p.name} (${p.currencySymbol})</option>`).join("")}
    </select>`;
  $("#select-pais").onchange = (e) => cambiarPais(e.target.value);
  pintarTextosMoneda();
}

/* Los textos que nombran la moneda (títulos, etiquetas) se actualizan al país
   activo y al idioma, para que no digan "bolívares" a un jugador colombiano ni
   "cartón" a uno que lee en inglés. */
function pintarTextosMoneda() {
  const sim = simboloMoneda();
  const nombre = nombreMoneda();
  const etiquetaPrecio = $("#etiqueta-precio");
  if (etiquetaPrecio) etiquetaPrecio.textContent = t("salas.precio", { moneda: sim });
  const etiquetaRetiro = $("#etiqueta-retiro-importe");
  if (etiquetaRetiro) etiquetaRetiro.textContent = t("retirar.importe", { moneda: sim });
  const notaPortada = $("#portada-nota");
  if (notaPortada) notaPortada.textContent = t("app.nota_portada", { moneda: nombre });
  const titulo2 = $("#hero-titulo2");
  if (titulo2) titulo2.textContent = t("hero.titulo2", { moneda: nombre });
  const comoP2 = $("#como-p2");
  if (comoP2) comoP2.textContent = t("como.p2_d", { moneda: nombre });
  const entradaSalas = $("#salas-entrada");
  if (entradaSalas) {
    const fuerte = t("salas.cobras");
    entradaSalas.innerHTML = t("salas.entrada", { fuerte: `<strong>${fuerte}</strong>` })
      .replace("{/fuerte}", "");
  }
  document.querySelectorAll("[data-moneda-placeholder]").forEach(
    (el) => (el.placeholder = sim + " 10,00"));
}

async function cambiarPais(code) {
  paisActual = code;
  localStorage.setItem(CLAVE_PAIS, code);
  paisInfo = catalogoPaises.find((p) => p.code === code) || paisInfo;
  // Se recarga todo para que los importes y el método de cobro sean los del país.
  pintarTextosMoneda();
  await cargarConfigRetiro();
  refrescarTodo();
  cargarSalas();
  avisar(t("aviso.pais_cambiado", { pais: paisInfo ? paisInfo.name : code }), "bien");
}

/* --- idioma --- */

async function cargarIdiomas() {
  if (!idiomaActual) idiomaActual = detectarIdioma();
  try {
    const cat = await get("/api/idiomas");
    idiomaInfo = (cat.idiomas || []).find((i) => i.code === idiomaActual) || null;
  } catch (err) { /* sin catálogo se queda el español */ }
  pintarSelectorIdioma();
}

function pintarSelectorIdioma() {
  const caja = $("#idioma-selector");
  if (!caja) return;
  caja.innerHTML = `
    <select id="select-idioma" aria-label="Idioma / Language / 语言">
      ${IDIOMAS.map((i) => `<option value="${i.code}"
        ${i.code === idiomaElegido() ? "selected" : ""}>${i.flag} ${i.name}</option>`).join("")}
    </select>`;
  $("#select-idioma").onchange = (e) => cambiarIdioma(e.target.value);
}

async function cambiarIdioma(code) {
  idiomaActual = code;
  localStorage.setItem(CLAVE_IDIOMA, code);
  idiomaInfo = IDIOMAS.find((i) => i.code === code) || null;
  aplicarIdioma();
  avisar(t("aviso.idioma_cambiado", { idioma: (idiomaInfo || {}).name || code }), "bien");
}

/* Vuelca el diccionario a todo lo que lleve data-i18n y repinta lo dinámico. */
function aplicarIdioma() {
  document.documentElement.lang = idiomaElegido();
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPh);
  });
  pintarTextosMoneda();
  pintarSesion();
  cargarConfigRetiro();
  refrescarTodo();
  cargarSalas();
}

async function refrescarRetiros() {
  const lista = $("#lista-retiros");
  if (!token) { lista.innerHTML = `<li class="vacio">${t("retirar.entra_ver")}</li>`; return; }
  try {
    const r = await get("/api/retiros");
    if (!r.retiros.length) {
      lista.innerHTML = `<li class="vacio">${t("retirar.sin_retiros")}</li>`;
      return;
    }
    lista.innerHTML = "";
    r.retiros.forEach((x) => {
      const li = document.createElement("li");
      const nombreMetodo = t("metodo." + x.metodo);
      const nombreEstado = t("retirar.estado_" + x.estado);
      li.innerHTML = `<span class="importe">${x.importe_texto}</span>
        <span>${nombreMetodo === "metodo." + x.metodo ? x.metodo.replace("_", " ") : nombreMetodo}</span>
        <span class="retiro-estado retiro-estado--${x.estado}">${
          nombreEstado === "retirar.estado_" + x.estado ? x.estado : nombreEstado}</span>`;
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
    if (s.foto_url) localStorage.setItem("bp777_foto", s.foto_url + "&t=" + Date.now());
    else localStorage.removeItem("bp777_foto");
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
// Primero el idioma (los textos), luego el país (la moneda), y al final las
// salas: así los importes ya salen en la moneda del país y en su idioma.
idiomaActual = idiomaActual || detectarIdioma();
aplicarIdioma();
cargarIdiomas().then(() => cargarPaises()).then(() => { cargarConfigRetiro(); cargarSalas(); });
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
