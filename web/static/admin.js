/* Panel de administración de Bingo Pirámide 777. */

const $ = (s) => document.querySelector(s);
const CLAVE_TOKEN = "bp777_token";

let token = localStorage.getItem(CLAVE_TOKEN) || "";
let jugadores = [];

async function pedir(ruta, opciones = {}) {
  const cabeceras = { "Content-Type": "application/json" };
  if (token) cabeceras["Authorization"] = "Bearer " + token;
  const r = await fetch(ruta, { ...opciones, headers: cabeceras });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "Error " + r.status);
  return d;
}
const get = (r) => pedir(r);
const post = (r, c) => pedir(r, { method: "POST", body: JSON.stringify(c || {}) });

let temporizador;
function avisar(mensaje, tipo = "") {
  const caja = $("#brindis");
  caja.textContent = mensaje;
  caja.className = "brindis" + (tipo ? " brindis--" + tipo : "");
  caja.hidden = false;
  clearTimeout(temporizador);
  temporizador = setTimeout(() => (caja.hidden = true), 4200);
}

function formatear(centimos) {
  const n = Math.abs(centimos);
  const entero = Math.floor(n / 100).toLocaleString("es-VE");
  return (centimos < 0 ? "-" : "") + "Bs " + entero + "," + String(n % 100).padStart(2, "0");
}

function fecha(ts) {
  return ts ? new Date(ts * 1000).toLocaleString("es-VE", { dateStyle: "short", timeStyle: "short" }) : "—";
}

/* --- sesión --- */

function pintarSesion(correo) {
  const caja = $("#sesion");
  caja.innerHTML = "";
  const quien = document.createElement("span");
  quien.textContent = correo || "";
  quien.style.color = "var(--gris)";
  const salir = document.createElement("button");
  salir.className = "boton boton--fantasma";
  salir.style.padding = ".4rem 1rem";
  salir.textContent = "Salir";
  salir.onclick = async () => {
    try { await post("/api/salir"); } catch (e) { /* da igual */ }
    localStorage.removeItem(CLAVE_TOKEN);
    localStorage.removeItem("bp777_correo");
    location.href = "/";
  };
  caja.append(quien, salir);
}

/* --- acceso --- */

function abrirAcceso() {
  $("#dialogo-contenido").innerHTML = `
    <h2>Entrar como administración</h2>
    <p style="color:var(--gris);font-size:.9rem">Usa la cuenta de administración.</p>
    <form id="form-acceso">
      <label>Correo<input type="email" name="correo" required value="bingopiramide777@gmail.com"></label>
      <label>Contraseña<input type="password" name="clave" required placeholder="••••••••"></label>
      <button class="boton boton--principal" type="submit">Entrar</button>
    </form>`;
  $("#dialogo").hidden = false;
  $("#dialogo-cerrar").onclick = () => ($("#dialogo").hidden = true);
  $("#form-acceso").onsubmit = async (e) => {
    e.preventDefault();
    const datos = Object.fromEntries(new FormData(e.target));
    try {
      const res = await post("/api/entrar", datos);
      if (!res.admin) throw new Error("Esa cuenta no es de administración.");
      token = res.token;
      localStorage.setItem(CLAVE_TOKEN, token);
      localStorage.setItem("bp777_correo", res.correo);
      $("#dialogo").hidden = true;
      pintarSesion(res.correo);
      cargarTodo();
    } catch (err) { avisar(err.message, "error"); }
  };
}

/* --- resumen --- */

async function cargarResumen() {
  const r = await get("/api/admin/resumen");
  const tarjetas = [
    ["Jugadores", r.jugadores, "cuentas activas"],
    ["Dinero en cuentas", formatear(r.total_en_cuentas), "saldo de todos"],
    ["Retiros pendientes", r.retiros_pendientes, formatear(r.total_pendiente) + " por pagar"],
    ["Partidas", r.partidas, "jugadas"],
    ["Apostado", formatear(r.apostado), "en cartones"],
    ["Pagado en premios", formatear(r.pagado), "a los ganadores"],
    ["Margen de la casa", formatear(r.margen), r.margen >= 0 ? "ganancia" : "pérdida"],
  ];
  $("#resumen").innerHTML = tarjetas.map(([t, v, p]) => `
    <div class="tarjeta-resumen">
      <p class="tarjeta-resumen__titulo">${t}</p>
      <p class="tarjeta-resumen__valor">${v}</p>
      <p class="tarjeta-resumen__pie">${p}</p>
    </div>`).join("");
}

/* --- retiros --- */

async function cargarRetiros() {
  const r = await get("/api/admin/retiros?estado=pendiente");
  const cuerpo = $("#tabla-retiros tbody");
  $("#contador-retiros").textContent = r.retiros.length + " pendiente(s)";
  if (!r.retiros.length) {
    cuerpo.innerHTML = '<tr><td colspan="6" class="vacio">No hay retiros pendientes.</td></tr>';
    return;
  }
  cuerpo.innerHTML = r.retiros.map((x) => `
    <tr>
      <td>${x.correo}</td>
      <td><strong>${x.importe_texto}</strong></td>
      <td>${x.metodo}</td>
      <td class="detalles">${x.detalles}</td>
      <td>${fecha(x.pedido)}</td>
      <td class="acciones-celda">
        <button class="boton boton--brillo" data-pagar="${x.id}">Pagar</button>
        <button class="boton boton--peligro" data-rechazar="${x.id}">Rechazar</button>
      </td>
    </tr>`).join("");
  cuerpo.querySelectorAll("[data-pagar]").forEach((b) => {
    b.onclick = () => resolverRetiro(b.dataset.pagar, "pagar");
  });
  cuerpo.querySelectorAll("[data-rechazar]").forEach((b) => {
    b.onclick = () => resolverRetiro(b.dataset.rechazar, "rechazar");
  });
}

function resolverRetiro(id, accion) {
  const esPago = accion === "pagar";
  $("#dialogo-contenido").innerHTML = `
    <h2>${esPago ? "Marcar como pagado" : "Rechazar retiro"}</h2>
    <p style="color:var(--gris);font-size:.9rem">
      ${esPago ? "Confirma que ya has hecho la transferencia al jugador."
               : "El dinero se devolverá al saldo del jugador."}
    </p>
    <form id="form-retiro">
      <label>Nota (opcional)<input type="text" name="nota" placeholder="Referencia, motivo…"></label>
      <button class="boton ${esPago ? "boton--brillo" : "boton--peligro"}" type="submit">
        ${esPago ? "Sí, ya pagué" : "Sí, rechazar y devolver"}
      </button>
    </form>`;
  $("#dialogo").hidden = false;
  $("#dialogo-cerrar").onclick = () => ($("#dialogo").hidden = true);
  $("#form-retiro").onsubmit = async (e) => {
    e.preventDefault();
    const nota = new FormData(e.target).get("nota") || "";
    try {
      await post("/api/admin/retiro", { id, accion, nota });
      $("#dialogo").hidden = true;
      avisar(esPago ? "Retiro marcado como pagado." : "Retiro rechazado y devuelto.", "bien");
      cargarTodo();
    } catch (err) { avisar(err.message, "error"); }
  };
}

/* --- jugadores --- */

async function cargarJugadores() {
  const r = await get("/api/admin/jugadores");
  jugadores = r.jugadores;
  pintarJugadores();
}

function pintarJugadores() {
  const filtro = ($("#buscar-jugador").value || "").toLowerCase();
  const lista = jugadores.filter((j) => j.correo.includes(filtro) || j.nombre.toLowerCase().includes(filtro));
  const cuerpo = $("#tabla-jugadores tbody");
  if (!lista.length) {
    cuerpo.innerHTML = '<tr><td colspan="7" class="vacio">Sin jugadores que mostrar.</td></tr>';
    return;
  }
  cuerpo.innerHTML = lista.map((j) => `
    <tr>
      <td>${j.correo}</td>
      <td>${j.nombre || "—"}</td>
      <td>${j.rol === "admin" ? '<span class="etiqueta-rol">admin</span>' : "jugador"}</td>
      <td><strong>${j.saldo_texto}</strong></td>
      <td>${fecha(j.creado)}</td>
      <td>${j.activo ? "activo" : "desactivado"}</td>
      <td class="acciones-celda">
        <button class="boton boton--fantasma boton--mini" data-ajuste="${j.correo}">Ajustar saldo</button>
        <button class="boton boton--fantasma boton--mini" data-estado="${j.correo}" data-activo="${j.activo}">
          ${j.activo ? "Desactivar" : "Activar"}
        </button>
      </td>
    </tr>`).join("");
  cuerpo.querySelectorAll("[data-ajuste]").forEach((b) => (b.onclick = () => ajustarSaldo(b.dataset.ajuste)));
  cuerpo.querySelectorAll("[data-estado]").forEach((b) => {
    b.onclick = async () => {
      try {
        await post("/api/admin/usuario", { correo: b.dataset.estado, activo: b.dataset.activo !== "true" });
        avisar("Estado cambiado.", "bien");
        cargarTodo();
      } catch (err) { avisar(err.message, "error"); }
    };
  });
}

function ajustarSaldo(correo) {
  $("#dialogo-contenido").innerHTML = `
    <h2>Ajustar saldo</h2>
    <p style="color:var(--gris);font-size:.9rem">${correo}</p>
    <form id="form-ajuste">
      <label>Importe (Bs)<input type="text" name="importe" required placeholder="100,00"></label>
      <label>Qué hacer
        <select name="signo">
          <option value="sumar">Sumar al saldo</option>
          <option value="restar">Restar del saldo</option>
        </select>
      </label>
      <button class="boton boton--principal" type="submit">Aplicar</button>
    </form>`;
  $("#dialogo").hidden = false;
  $("#dialogo-cerrar").onclick = () => ($("#dialogo").hidden = true);
  $("#form-ajuste").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      const res = await post("/api/admin/ajuste", { correo, importe: d.importe, signo: d.signo });
      $("#dialogo").hidden = true;
      avisar("Saldo actualizado: " + res.saldo_texto, "bien");
      cargarTodo();
    } catch (err) { avisar(err.message, "error"); }
  };
}

/* --- partidas y movimientos --- */

async function cargarPartidas() {
  const r = await get("/api/admin/partidas");
  const cuerpo = $("#tabla-partidas tbody");
  if (!r.partidas.length) {
    cuerpo.innerHTML = '<tr><td colspan="8" class="vacio">Todavía no hay partidas.</td></tr>';
    return;
  }
  cuerpo.innerHTML = r.partidas.map((p) => `
    <tr>
      <td><code>${p.id}</code></td>
      <td>${p.patron}</td>
      <td>${p.estado}</td>
      <td>${p.cartones}</td>
      <td>${p.bolas}</td>
      <td>${p.apostado_texto}</td>
      <td>${p.ganador || "—"}</td>
      <td>${p.premio_texto}</td>
    </tr>`).join("");
}

async function cargarMovimientos() {
  const r = await get("/api/admin/movimientos");
  const cuerpo = $("#tabla-movimientos tbody");
  if (!r.movimientos.length) {
    cuerpo.innerHTML = '<tr><td colspan="5" class="vacio">Sin movimientos.</td></tr>';
    return;
  }
  cuerpo.innerHTML = r.movimientos.map((m) => `
    <tr>
      <td>${m.correo}</td>
      <td>${m.tipo}</td>
      <td class="${m.centimos > 0 ? "positivo" : "negativo"}">${m.importe_texto}</td>
      <td>${formatear(m.saldo_despues)}</td>
      <td>${m.motivo || "—"}</td>
    </tr>`).join("");
}

/* --- arranque --- */

async function cargarTodo() {
  if (!token) { abrirAcceso(); return; }
  try {
    const s = await get("/api/saldo");
    if (!s.admin) throw new Error("Esa cuenta no es de administración.");
    pintarSesion(localStorage.getItem("bp777_correo"));
    await Promise.all([cargarResumen(), cargarRetiros(), cargarJugadores(), cargarPartidas(), cargarMovimientos()]);
  } catch (err) {
    avisar(err.message, "error");
    localStorage.removeItem(CLAVE_TOKEN);
    abrirAcceso();
  }
}

$("#buscar-jugador").oninput = pintarJugadores;
cargarTodo();
setInterval(() => { if (token) { cargarResumen(); cargarRetiros(); } }, 20000);
