/* Panel de administración de Bingo Pirámide 777. */

const $ = (s) => document.querySelector(s);
const CLAVE_TOKEN = "bp777_token";

let token = localStorage.getItem(CLAVE_TOKEN) || "";
let jugadores = [];

// Métodos de pago de todos los países y su bandera, para la cola de depósitos.
const NOMBRES_METODO = {
  paypal: "PayPal", cripto: "USDT (cripto)",
};
const BANDERAS_PAIS = { VE: "🇻🇪", CO: "🇨🇴", CL: "🇨🇱", US: "🇺🇸" };
const banderaPais = (code) => BANDERAS_PAIS[code] || "🏳️";

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
  return (centimos < 0 ? "-" : "") + "$ " + entero + "," + String(n % 100).padStart(2, "0");
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
  asegurarCapa();
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

/* --- diálogo --- */

function abrirDialogo(html) {
  $("#dialogo-contenido").innerHTML = html;
  $("#dialogo").hidden = false;
  $("#dialogo-cerrar").onclick = () => ($("#dialogo").hidden = true);
}

const cuerpo = (clave) => document.getElementById("cuerpo-" + clave);

/* --- resumen --- */

async function cargarResumen() {
  const caja = cuerpo("resumen");
  if (!caja) return;
  const r = await get("/api/admin/resumen");
  const tarjetas = [
    ["Jugadores", r.jugadores, "cuentas activas"],
    ["Dinero en cuentas", formatear(r.total_en_cuentas), "saldo de todos"],
    ["Retiros pendientes", r.retiros_pendientes, formatear(r.total_pendiente) + " por pagar"],
    ["Comisión de depósitos", formatear(r.depositos_comision), "20% retenido al acreditar"],
    ["Partidas", r.partidas, "jugadas"],
    ["Apostado", formatear(r.apostado), "en cartones"],
    ["Pagado en premios", formatear(r.pagado), "a los ganadores"],
    ["Margen de la casa", formatear(r.margen), r.margen >= 0 ? "ganancia" : "pérdida"],
  ];
  caja.innerHTML = `<div class="tarjetas-resumen">${tarjetas.map(([t, v, p]) => `
    <div class="tarjeta-resumen">
      <p class="tarjeta-resumen__titulo">${t}</p>
      <p class="tarjeta-resumen__valor">${v}</p>
      <p class="tarjeta-resumen__pie">${p}</p>
    </div>`).join("")}</div>`;
}

/* --- retiros --- */

async function cargarRetiros() {
  const caja = cuerpo("retiros");
  if (!caja) return;
  const r = await get("/api/admin/retiros?estado=pendiente");
  caja.innerHTML = `
    <div class="panel__cabecera">
      <div class="pastilla">${r.retiros.length} pendiente(s)</div>
    </div>
    <div class="tabla-envoltorio"><table class="tabla">
      <thead><tr><th>Jugador</th><th>Importe</th><th>Método</th><th>Datos</th>
        <th>Pedido</th><th>Acciones</th></tr></thead>
      <tbody>${r.retiros.length ? r.retiros.map((x) => `
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
        </tr>`).join("") : '<tr><td colspan="6" class="vacio">No hay retiros pendientes.</td></tr>'}
      </tbody></table></div>`;
  caja.querySelectorAll("[data-pagar]").forEach((b) =>
    (b.onclick = () => resolverRetiro(b.dataset.pagar, "pagar")));
  caja.querySelectorAll("[data-rechazar]").forEach((b) =>
    (b.onclick = () => resolverRetiro(b.dataset.rechazar, "rechazar")));
}

function resolverRetiro(id, accion) {
  const esPago = accion === "pagar";
  abrirDialogo(`
    <h2>${esPago ? "Marcar como pagado" : "Rechazar retiro"}</h2>
    <p style="color:var(--gris);font-size:.9rem">
      ${esPago ? "Confirma que ya has hecho el pago al jugador (PayPal o USDT)."
               : "El dinero se devolverá al saldo del jugador."}
    </p>
    <form id="form-retiro">
      <label>Nota (opcional)<input type="text" name="nota" placeholder="Referencia, motivo…"></label>
      <button class="boton ${esPago ? "boton--brillo" : "boton--peligro"}" type="submit">
        ${esPago ? "Sí, ya pagué" : "Sí, rechazar y devolver"}
      </button>
    </form>`);
  $("#form-retiro").onsubmit = async (e) => {
    e.preventDefault();
    const nota = new FormData(e.target).get("nota") || "";
    try {
      await post("/api/admin/retiro", { id, accion, nota });
      $("#dialogo").hidden = true;
      avisar(esPago ? "Retiro marcado como pagado." : "Retiro rechazado y devuelto.", "bien");
      cargarRetiros();
      if (abiertas.has("resumen")) cargarResumen();
    } catch (err) { avisar(err.message, "error"); }
  };
}

/* --- depósitos --- */

async function cargarDepositos() { return refrescarDepositos(); }

async function refrescarDepositos() {
  const caja = cuerpo("depositos");
  if (!caja) return;
  const res = await get("/api/admin/depositos?estado=pendiente");
  caja.innerHTML = `
    <div class="panel__cabecera">
      <div class="pastilla">${res.depositos.length} por revisar</div>
    </div>
    <p class="entrada">Pagos declarados por los jugadores (PayPal o USDT (cripto)).
       Comprueba la referencia antes de acreditar.</p>
    <div class="tabla-scroll"><table class="tabla">
      <thead><tr><th>Jugador</th><th>Monto</th><th>País</th><th>Método</th><th>Referencia</th>
        <th>Día</th><th>Acciones</th></tr></thead>
      <tbody>${res.depositos.length ? res.depositos.map((d) => `
        <tr>
          <td>${d.correo}</td>
          <td><strong>${d.importe_texto}</strong></td>
          <td>${banderaPais(d.pais)} ${d.pais || "VE"}</td>
          <td>${NOMBRES_METODO[d.metodo] || d.metodo}</td>
          <td class="mono">${d.referencia}</td>
          <td>${d.dia}</td>
          <td class="acciones-celda">
            <button class="boton boton--brillo boton--mini" data-acreditar="${d.id}">Acreditar</button>
            <button class="boton boton--fantasma boton--mini" data-rechazar="${d.id}">Rechazar</button>
          </td>
        </tr>`).join("") : '<tr><td colspan="8" class="vacio">No hay depósitos por revisar.</td></tr>'}
      </tbody></table></div>`;
  caja.querySelectorAll("[data-acreditar]").forEach((b) =>
    (b.onclick = () => resolverDeposito(b.dataset.acreditar, "acreditar")));
  caja.querySelectorAll("[data-rechazar]").forEach((b) =>
    (b.onclick = () => resolverDeposito(b.dataset.rechazar, "rechazar")));
}

async function resolverDeposito(id, accion) {
  const palabra = accion === "acreditar" ? "Acreditar" : "Rechazar";
  const aviso = accion === "acreditar"
    ? "Se sumará el dinero al saldo del jugador. ¿Comprobaste la referencia en el banco?"
    : "No se moverá dinero. ¿Seguro?";
  if (!confirm(`${palabra} este depósito.\n\n${aviso}`)) return;
  try {
    await post("/api/admin/deposito", { id, accion });
    avisar(accion === "acreditar" ? "Depósito acreditado." : "Depósito rechazado.", "bien");
    refrescarDepositos();
    if (abiertas.has("resumen")) cargarResumen();
  } catch (err) { avisar(err.message, "error"); }
}

/* --- jugadores --- */

async function cargarJugadores() {
  const caja = cuerpo("jugadores");
  if (!caja) return;
  const r = await get("/api/admin/jugadores");
  jugadores = r.jugadores;
  caja.innerHTML = `
    <div class="panel__cabecera">
      <div class="acciones acciones--pegadas">
        <input type="text" id="buscar-jugador" placeholder="Buscar por correo…" aria-label="Buscar jugador">
      </div>
    </div>
    <div class="tabla-envoltorio"><table class="tabla" id="tabla-jugadores">
      <thead><tr><th>Correo</th><th>Nombre</th><th>Rol</th><th>Saldo</th><th>Comisión</th><th>Alta</th>
        <th>Estado</th><th>Ajuste</th></tr></thead>
      <tbody></tbody>
    </table></div>`;
  $("#buscar-jugador").oninput = pintarJugadores;
  pintarJugadores();
}

function pintarJugadores() {
  const buscador = $("#buscar-jugador");
  const filtro = ((buscador && buscador.value) || "").toLowerCase();
  const lista = jugadores.filter((j) =>
    j.correo.includes(filtro) || (j.nombre || "").toLowerCase().includes(filtro));
  const cuerpoTabla = $("#tabla-jugadores tbody");
  if (!cuerpoTabla) return;
  if (!lista.length) {
    cuerpoTabla.innerHTML = '<tr><td colspan="8" class="vacio">Sin jugadores que mostrar.</td></tr>';
    return;
  }
  cuerpoTabla.innerHTML = lista.map((j) => `
    <tr>
      <td>${j.correo}</td>
      <td>${j.nombre || "—"}</td>
      <td>${j.rol === "admin" ? '<span class="etiqueta-rol">admin</span>' : "jugador"}</td>
      <td><strong>${j.saldo_texto}</strong></td>
      <td>${j.comision_pct >= 0 ? `<strong>${j.comision_pct} %</strong>` : '<span style="color:var(--gris)">10 % fijo</span>'}</td>
      <td>${fecha(j.creado)}</td>
      <td>${j.activo ? "activo" : "desactivado"}${j.pregunta ? ' · <span class="etiqueta-rol">con pregunta</span>' : ""}</td>
      <td class="acciones-celda">
        <button class="boton boton--fantasma boton--mini" data-comision="${j.correo}" data-pct="${j.comision_pct}">Comisión</button>
        <button class="boton boton--fantasma boton--mini" data-ajuste="${j.correo}">Ajustar saldo</button>
        <button class="boton boton--fantasma boton--mini" data-clave="${j.correo}">Restablecer clave</button>
        <button class="boton boton--fantasma boton--mini" data-estado="${j.correo}" data-activo="${j.activo}">
          ${j.activo ? "Desactivar" : "Activar"}
        </button>
      </td>
    </tr>`).join("");
  cuerpoTabla.querySelectorAll("[data-comision]").forEach((b) =>
    (b.onclick = () => editarComision(b.dataset.comision, parseInt(b.dataset.pct, 10))));
  cuerpoTabla.querySelectorAll("[data-ajuste]").forEach((b) =>
    (b.onclick = () => ajustarSaldo(b.dataset.ajuste)));
  cuerpoTabla.querySelectorAll("[data-clave]").forEach((b) =>
    (b.onclick = () => restablecerClave(b.dataset.clave)));
  cuerpoTabla.querySelectorAll("[data-estado]").forEach((b) => {
    b.onclick = async () => {
      try {
        await post("/api/admin/usuario",
          { correo: b.dataset.estado, activo: b.dataset.activo !== "true" });
        avisar("Estado cambiado.", "bien");
        cargarJugadores();
      } catch (err) { avisar(err.message, "error"); }
    };
  });
}

function editarComision(correo, pctActual) {
  const actual = Number.isFinite(pctActual) ? pctActual : -1;
  abrirDialogo(`
    <h2>Comisión de anfitrión</h2>
    <p style="color:var(--gris);font-size:.9rem">${correo}</p>
    <form id="form-comision">
      <label>Porcentaje que cobra por cada bote de sus salas (%)
        <input type="number" name="pct" min="-1" max="90" step="1"
               value="${actual}" required>
      </label>
      <p class="ayuda">Escribe <strong>-1</strong> para dejar el 10 % fijo de las salas de jugador.
         Del 0 al 90 fija el porcentaje de esta cuenta: el premio del ganador no cambia,
         lo que cambia es la parte del anfitrión.</p>
      <button class="boton boton--principal" type="submit">Guardar</button>
    </form>`);
  $("#form-comision").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      await post("/api/admin/usuario", { correo, comision_pct: parseInt(d.pct, 10) });
      $("#dialogo").hidden = true;
      avisar("Comisión actualizada.", "bien");
      cargarJugadores();
    } catch (err) { avisar(err.message, "error"); }
  };
}

function ajustarSaldo(correo) {
  abrirDialogo(`
    <h2>Ajustar saldo</h2>
    <p style="color:var(--gris);font-size:.9rem">${correo}</p>
    <form id="form-ajuste">
      <label>Importe ($)<input type="text" name="importe" required placeholder="100,00"></label>
      <label>Qué hacer
        <select name="signo">
          <option value="sumar">Sumar al saldo</option>
          <option value="restar">Restar del saldo</option>
        </select>
      </label>
      <button class="boton boton--principal" type="submit">Aplicar</button>
    </form>`);
  $("#form-ajuste").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      const res = await post("/api/admin/ajuste", { correo, importe: d.importe, signo: d.signo });
      $("#dialogo").hidden = true;
      avisar("Saldo actualizado: " + res.saldo_texto, "bien");
      cargarJugadores();
      if (abiertas.has("resumen")) cargarResumen();
    } catch (err) { avisar(err.message, "error"); }
  };
}

function restablecerClave(correo) {
  abrirDialogo(`
    <h2>Restablecer contraseña</h2>
    <p style="color:var(--gris);font-size:.9rem">${correo}</p>
    <p style="font-size:.9rem">Se pondrá una contraseña nueva y se cerrarán <strong>todas</strong>
       sus sesiones abiertas. Pásasela al jugador por WhatsApp.</p>
    <form id="form-clave">
      <label>Contraseña nueva (déjalo vacío para generar una)
        <input type="text" name="clave" placeholder="Automática">
      </label>
      <button class="boton boton--principal" type="submit">Restablecer</button>
    </form>`);
  $("#form-clave").onsubmit = async (e) => {
    e.preventDefault();
    const clave = new FormData(e.target).get("clave") || "";
    try {
      const res = await post("/api/admin/restablecer", { correo, clave });
      abrirDialogo(`
        <h2>Contraseña restablecida</h2>
        <p style="color:var(--gris);font-size:.9rem">${correo}</p>
        <p>Pásale esta contraseña al jugador. No se vuelve a mostrar.</p>
        <p class="clave-temporal">${res.clave}</p>
        <button class="boton boton--brillo boton--alto" id="copiar-clave">Copiar</button>
        <p class="ayuda">Sus sesiones abiertas quedaron cerradas.</p>`);
      $("#copiar-clave").onclick = async () => {
        try { await navigator.clipboard.writeText(res.clave); avisar("Copiada.", "bien"); }
        catch (err) { avisar("Cópiala a mano.", "error"); }
      };
    } catch (err) { avisar(err.message, "error"); }
  };
}

/* --- partidas y movimientos --- */

async function cargarPartidas() {
  const caja = cuerpo("partidas");
  if (!caja) return;
  const r = await get("/api/admin/partidas");
  caja.innerHTML = `<div class="tabla-envoltorio"><table class="tabla">
    <thead><tr><th>Partida</th><th>Patrón</th><th>Estado</th><th>Cartones</th><th>Bolas</th>
      <th>Apostado</th><th>Ganador</th><th>Premio</th></tr></thead>
    <tbody>${r.partidas.length ? r.partidas.map((p) => `
      <tr>
        <td><code>${p.id}</code></td>
        <td>${p.patron}</td>
        <td>${p.estado}</td>
        <td>${p.cartones}</td>
        <td>${p.bolas}</td>
        <td>${p.apostado_texto}</td>
        <td>${p.ganador || "—"}</td>
        <td>${p.premio_texto}</td>
      </tr>`).join("") : '<tr><td colspan="8" class="vacio">Todavía no hay partidas.</td></tr>'}
    </tbody></table></div>`;
}

async function cargarMovimientos() {
  const caja = cuerpo("movimientos");
  if (!caja) return;
  const r = await get("/api/admin/movimientos");
  caja.innerHTML = `<div class="tabla-envoltorio"><table class="tabla">
    <thead><tr><th>Jugador</th><th>Tipo</th><th>Importe</th><th>Saldo después</th>
      <th>Motivo</th></tr></thead>
    <tbody>${r.movimientos.length ? r.movimientos.map((m) => `
      <tr>
        <td>${m.correo}</td>
        <td>${m.tipo}</td>
        <td class="${m.centimos > 0 ? "positivo" : "negativo"}">${m.importe_texto}</td>
        <td>${formatear(m.saldo_despues)}</td>
        <td>${m.motivo || "—"}</td>
      </tr>`).join("") : '<tr><td colspan="5" class="vacio">Sin movimientos.</td></tr>'}
    </tbody></table></div>`;
}

/* --- sistema de cobro --- */

// Todo lo que se cobra, en un solo sitio, y la prueba de que no se cobra dos veces.
async function cargarCobros() {
  const caja = cuerpo("cobros");
  if (!caja) return;
  const r = await get("/api/admin/cobros");
  const a = r.auditoria || {};
  const t = r.totales || {};

  const definicion = (r.definicion || []).map((d) => `
    <tr>
      <td><strong>${d.titulo}</strong></td>
      <td>${d.pct === null ? "según el entorno" : d.pct + " %"}</td>
      <td>${d.quien}</td>
      <td>${d.cuando}</td>
      <td>${d.sobre}</td>
    </tr>`).join("");

  const tarjetas = [
    ["Comisión de depósito", t.deposito_comision_texto, `${t.deposito_pct} % de cada depósito (una vez)`],
    ["Comisiones a anfitriones", t.anfitrion_texto, "una vez por partida"],
    ["Ganancia de la app (bingo)", t.app_bingo_texto, "incluye el 5 % de la sala de trabajo"],
    ["Ganancia de la app (depósitos)", t.app_depositos_texto, "comisión anti-lavado"],
    ["Ganancia total de la app", t.app_total_texto, "bingo + depósitos"],
    ["Comisiones a padrinos", t.padrinos_texto, "de la parte de la app"],
  ];

  caja.innerHTML = `
    <div class="aviso-cobro ${a.sin_duplicados ? "aviso-cobro--bien" : "aviso-cobro--mal"}">
      <strong>${a.sin_duplicados ? "Sin cobros duplicados" : "¡Ojo: hay cobros duplicados!"}</strong>
      <p>${a.sin_duplicados
        ? "La auditoría no encuentra ningún cobro repetido: el 20 % del depósito se cobra una sola vez y cada comisión de sala, una vez por partida."
        : (a.avisos || []).join(" ")}</p>
      <p class="ayuda">Depósitos acreditados: ${a.depositos_acreditados || 0} ·
         partidas terminadas: ${a.partidas_terminadas || 0} ·
         referidos anotados: ${a.referidos_anotados || 0}</p>
    </div>

    <div class="tarjetas-resumen">${tarjetas.map(([titulo, valor, pie]) => `
      <div class="tarjeta-resumen">
        <p class="tarjeta-resumen__titulo">${titulo}</p>
        <p class="tarjeta-resumen__valor">${valor}</p>
        <p class="tarjeta-resumen__pie">${pie}</p>
      </div>`).join("")}</div>

    <h3>Qué se cobra y a quién</h3>
    <div class="tabla-envoltorio"><table class="tabla">
      <thead><tr><th>Cobro</th><th>%</th><th>Quién cobra</th><th>Cuándo</th><th>Sobre qué</th></tr></thead>
      <tbody>${definicion}</tbody>
    </table></div>
    <p class="ayuda">La sala "Gana dinero desde casa con BingoPiramide777" reparte el bote
       así: ganador 80 %, anfitrión 15 % y app 5 %. Como el anfitrión de esa sala es la
       propia administración, esa cuenta se queda el 20 % del bote (15 % + 5 %). Es dinero
       distinto del 20 % que se retiene en los depósitos: uno es sobre lo que entra y el
       otro sobre el bote. Los dos se cobran una sola vez.</p>`;
}

/* --- ganancias --- */

async function cargarGanancias() {
  const caja = cuerpo("ganancias");
  if (!caja) return;
  const r = await get("/api/admin/resumen");
  const e = r.economia || {};
  const tarjetas = [
    ["Partidas terminadas", e.partidas || 0, "jugadas"],
    ["Botes totales", e.botes_texto, "apostado en cartones"],
    ["Premios pagados", e.premios_texto, "a los ganadores (75%-80%)"],
    ["Comisiones a anfitriones", e.comisiones_texto, "salas de jugador (10%) y de trabajo (15%)"],
    ["Comisión de depósitos", formatear(e.depositos_comision || 0), "20% retenido al acreditar"],
    ["Ganancia de la app", e.app_total_texto || e.app_texto, "bingo + depósitos"],
  ];
  caja.innerHTML = `
    <p class="entrada">En las salas de la casa el ganador cobra el 80% y la app el 20%. En las
       salas de jugador el ganador cobra el 75%, el anfitrión el 10% y la app el 15%. En la sala
       de trabajo ("Gana dinero desde casa") el ganador cobra el 80%, el anfitrión el 15% y la app
       el 5%. Además, la app retiene un 20% de cada depósito al acreditarlo.</p>
    <div class="tarjetas-resumen">${tarjetas.map(([t, v, p]) => `
      <div class="tarjeta-resumen">
        <p class="tarjeta-resumen__titulo">${t}</p>
        <p class="tarjeta-resumen__valor">${v}</p>
        <p class="tarjeta-resumen__pie">${p}</p>
      </div>`).join("")}</div>`;
}

/* --- referidos --- */

async function cargarReferidosAdmin() {
  const caja = cuerpo("referidos");
  if (!caja) return;
  const r = await get("/api/admin/referidos");
  const porPais = r.economia_pais || [];
  const tarjetas = [
    ["Comisión de padrinos", r.pct + "%", "de la ganancia de la app"],
    ["Total pagado", r.total_texto, "a padrinos"],
  ];
  caja.innerHTML = `
    <p class="entrada">Cada padrino cobra el ${r.pct}% de lo que la app gana cuando
       uno de sus invitados canta bingo. Sale de la parte de la app: el premio del
       ganador y la comisión del anfitrión no se tocan.</p>
    <div class="tarjetas-resumen">${tarjetas.map(([t, v, p]) => `
      <div class="tarjeta-resumen">
        <p class="tarjeta-resumen__titulo">${t}</p>
        <p class="tarjeta-resumen__valor">${v}</p>
        <p class="tarjeta-resumen__pie">${p}</p>
      </div>`).join("")}</div>
    <h3>Ganancia de la app por país</h3>
    <div class="tabla-envoltorio"><table class="tabla">
      <thead><tr><th>País</th><th>Ganancia de la app</th></tr></thead>
      <tbody>${porPais.length ? porPais.map((p) => `
        <tr><td>${p.pais}</td><td>${p.app_texto}</td></tr>`).join("")
        : '<tr><td colspan="2" class="vacio">Sin datos todavía.</td></tr>'}
      </tbody></table></div>
    <h3>Últimas comisiones</h3>
    <div class="tabla-envoltorio"><table class="tabla">
      <thead><tr><th>Padrino</th><th>Invitado</th><th>Comisión</th><th>Partida</th></tr></thead>
      <tbody>${r.referidos.length ? r.referidos.map((f) => `
        <tr><td>${f.padrino}</td><td>${f.referido}</td>
          <td>${f.texto}</td><td>${f.partida}</td></tr>`).join("")
        : '<tr><td colspan="4" class="vacio">Sin comisiones todavía.</td></tr>'}
      </tbody></table></div>`;
}

/* --- torneos (sala de evento) --- */

async function cargarTorneos() {
  const caja = cuerpo("torneos");
  if (!caja) return;
  const res = await get("/api/admin/salas");
  const evento = res.evento || {};
  const premios = (evento.premios || []).map((p) =>
    `<div class="premio"><div class="premio__puesto">${p.puesto}º</div>
       <div class="premio__importe">${p.premio_texto}</div>
       <div class="premio__pct">${p.pct_texto} del bote</div></div>`).join("");
  caja.innerHTML = `
    <p class="entrada">El torneo es una sala especial que reparte el bote entre varios puestos.
       Configúralo aquí: precio del cartón, aforo, premios por porcentaje y fecha.</p>
    <div class="tarjetas-resumen">
      <div class="tarjeta-resumen">
        <p class="tarjeta-resumen__titulo">Estado</p>
        <p class="tarjeta-resumen__valor">${evento.activa ? "Abierto" : "Cerrado"}</p>
        <p class="tarjeta-resumen__pie">${evento.nombre || "Torneo"}</p>
      </div>
      <div class="tarjeta-resumen">
        <p class="tarjeta-resumen__titulo">Jugadores</p>
        <p class="tarjeta-resumen__valor">${evento.jugadores ?? 0}</p>
        <p class="tarjeta-resumen__pie">${evento.aforo_texto || "Sin límite"}</p>
      </div>
      <div class="tarjeta-resumen">
        <p class="tarjeta-resumen__titulo">Bote</p>
        <p class="tarjeta-resumen__valor">${evento.bote_texto || "—"}</p>
        <p class="tarjeta-resumen__pie">Cartón ${evento.precio_texto || "—"}</p>
      </div>
      <div class="tarjeta-resumen">
        <p class="tarjeta-resumen__titulo">Fecha</p>
        <p class="tarjeta-resumen__valor" style="font-size:1rem">${evento.fecha_partida || "—"}</p>
        <p class="tarjeta-resumen__pie">cuándo se juega</p>
      </div>
    </div>
    <div class="evento__premios" style="margin:1rem 0">${premios || '<p class="ayuda">Sin premios configurados.</p>'}</div>
    <button class="boton boton--principal boton--alto" id="btn-config-torneo">Configurar el torneo</button>`;
  $("#btn-config-torneo").onclick = () => editarTorneo(evento);
}

async function editarTorneo(evento) {
  const tipos = await tiposDeJuego();
  const opciones = tipos.map((t) =>
    `<option value="${t.id}" ${t.id === evento.tipo_juego ? "selected" : ""}>${t.nombre}</option>`).join("");
  const pctActual = (evento.premios || []).map((p) => p.pct).join(",") || "70,20,10";
  abrirDialogo(`
    <h2>Configurar el torneo</h2>
    <p style="color:var(--gris);font-size:.9rem">Sala de evento: reparte el bote entre los puestos.</p>
    <form id="form-torneo">
      <label>Nombre<input type="text" name="nombre" value="${evento.nombre || "Torneo del día"}" maxlength="40"></label>
      <label>Precio del cartón ($)
        <input type="text" name="precio" value="${(evento.precio_texto || "").replace("$ ", "")}" required>
      </label>
      <label>Aforo (0 = sin límite)
        <input type="number" name="aforo" min="0" step="1" value="${evento.aforo || 0}">
      </label>
      <label>Premios por porcentaje (separados por coma, de 1º a último)
        <input type="text" name="premios_pct" value="${pctActual}" placeholder="70,20,10">
      </label>
      <label>Tipo de juego<select name="tipo_juego">${opciones}</select></label>
      <label>Cartones a la venta (0 = sin tope)
        <input type="number" name="cupo_cartones" min="0" step="1" value="${evento.cupo_cartones || 0}">
      </label>
      <label>Fecha de la partida
        <input type="text" name="fecha_partida" maxlength="60" placeholder="Ej.: hoy 8:00 pm"
               value="${evento.fecha_partida || ""}">
      </label>
      <label>¿Abierto?
        <select name="activa">
          <option value="si" ${evento.activa ? "selected" : ""}>Sí, abierto</option>
          <option value="no" ${!evento.activa ? "selected" : ""}>No, cerrado</option>
        </select>
      </label>
      <button class="boton boton--principal" type="submit">Guardar torneo</button>
    </form>
    <p class="ayuda">Los porcentajes no pueden sumar más de 100 %. Lo que sobre queda para la app.</p>`);
  $("#form-torneo").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      await post("/api/admin/evento", {
        nombre: d.nombre, precio: d.precio, aforo: d.aforo,
        premios_pct: d.premios_pct, tipo_juego: d.tipo_juego,
        cupo_cartones: d.cupo_cartones, fecha_partida: d.fecha_partida,
        activa: d.activa === "si",
      });
      $("#dialogo").hidden = true;
      avisar("Torneo actualizado.", "bien");
      cargarTorneos();
    } catch (err) { avisar(err.message, "error"); }
  };
}

/* --- Glenis IA --- */

let historialGlenis = [];
function burbuja(quien, texto, clase = "") {
  const div = document.createElement("div");
  div.className = `chat__burbuja chat__burbuja--${clase}`;
  if (clase === "glenis") {
    const cara = document.createElement("img");
    cara.className = "chat__cara";
    cara.src = "/emblema.svg";
    cara.alt = "Glenis IA";
    div.appendChild(cara);
  }
  const nombre = document.createElement("div");
  nombre.className = "chat__quien";
  nombre.textContent = quien;
  const cuerpoTexto = document.createElement("div");
  cuerpoTexto.textContent = texto;
  div.append(nombre, cuerpoTexto);
  return div;
}

function pintarMensaje(quien, texto, clase) {
  const caja = $("#chat-mensajes");
  if (!caja) return;
  caja.appendChild(burbuja(quien, texto, clase));
  caja.scrollTop = caja.scrollHeight;
}

async function cargarGlenis() {
  const caja = cuerpo("glenis");
  if (!caja) return;
  caja.innerHTML = `
    <p class="entrada">Tu asistente. Pregúntale por el dinero, los jugadores o los depósitos,
       o pídele que anote o acredite algo. Lo que toca dinero queda registrado a su nombre.</p>
    <div class="chat" id="chat-glenis">
      <div class="chat__mensajes" id="chat-mensajes"></div>
      <form class="chat__form" id="chat-form">
        <input type="text" id="chat-texto" placeholder="Escríbele a Glenis…" autocomplete="off">
        <button class="boton boton--brillo" type="submit">Enviar</button>
      </form>
      <div class="chat__sugerencias">
        <button class="pastilla pastilla--boton" data-sugerencia="Dame el resumen del día">Resumen del día</button>
        <button class="pastilla pastilla--boton" data-sugerencia="¿Qué depósitos hay pendientes?">Depósitos pendientes</button>
        <button class="pastilla pastilla--boton" data-sugerencia="¿Qué retiros hay pendientes?">Retiros pendientes</button>
        <button class="pastilla pastilla--boton" data-sugerencia="¿Cuánto dinero hay en las cuentas?">Dinero en cuentas</button>
      </div>
    </div>`;
  $("#chat-form").onsubmit = (e) => {
    e.preventDefault();
    hablarConGlenis($("#chat-texto").value);
  };
  caja.querySelectorAll("[data-sugerencia]").forEach((b) =>
    (b.onclick = () => hablarConGlenis(b.dataset.sugerencia)));
  try {
    const res = await get("/api/admin/glenis");
    if (!res.historial.length) {
      pintarMensaje("Glenis IA", "¡Hola! Soy Glenis. Pregúntame por el dinero, los jugadores "
        + "o los depósitos, o pídeme que anote algo. ¿Qué necesitas?", "glenis");
    } else {
      res.historial.slice(-12).forEach((m) =>
        pintarMensaje(m.quien, m.texto, m.quien === "Glenis IA" ? "glenis" : "yo"));
    }
    historialGlenis = res.historial.map((m) => ({
      role: m.quien === "Glenis IA" ? "assistant" : "user", content: m.texto,
    }));
  } catch (err) { avisar(err.message, "error"); }
}

async function hablarConGlenis(texto) {
  if (!texto.trim()) return;
  pintarMensaje("Tú", texto, "yo");
  historialGlenis.push({ role: "user", content: texto });
  const cajaTexto = $("#chat-texto");
  if (cajaTexto) cajaTexto.value = "";
  pintarMensaje("Glenis IA", "…", "glenis");
  const puntos = $("#chat-mensajes").lastChild;
  try {
    const res = await post("/api/admin/glenis", { mensaje: texto, historial: historialGlenis });
    puntos.remove();
    pintarMensaje("Glenis IA", res.respuesta, "glenis");
    historialGlenis.push({ role: "assistant", content: res.respuesta });
    if (res.acciones && res.acciones.length) {
      const hechas = res.acciones.map((a) => a.herramienta).join(", ");
      pintarMensaje("Sistema", `Consultó y ejecutó: ${hechas}`, "error");
      if (abiertas.has("depositos")) refrescarDepositos();
      if (abiertas.has("resumen")) cargarResumen();
    }
  } catch (err) {
    if (puntos && puntos.parentNode) puntos.remove();
    pintarMensaje("Glenis IA", err.message, "error");
  }
}

/* --- ventanas emergentes --- */

// Cada apartado vive en su propia ventana: al abrirla se carga solo lo suyo.
const VENTANAS = {
  resumen:     { titulo: "Resumen",               cargar: () => cargarResumen() },
  glenis:      { titulo: "Glenis IA",             cargar: () => cargarGlenis() },
  torneos:     { titulo: "Torneos",               cargar: () => cargarTorneos() },
  depositos:   { titulo: "Depósitos por revisar", cargar: () => refrescarDepositos() },
  retiros:     { titulo: "Retiros pendientes",    cargar: () => cargarRetiros() },
  jugadores:   { titulo: "Jugadores",             cargar: () => cargarJugadores() },
  partidas:    { titulo: "Partidas",              cargar: () => cargarPartidas() },
  salas:       { titulo: "Salas en vivo",         cargar: () => cargarSalasAdmin() },
  cobros:      { titulo: "Sistema de cobro",      cargar: () => cargarCobros() },
  ganancias:   { titulo: "Ganancias del bingo",   cargar: () => cargarGanancias() },
  referidos:   { titulo: "Referidos",             cargar: () => cargarReferidosAdmin() },
  movimientos: { titulo: "Últimos movimientos",   cargar: () => cargarMovimientos() },
};

const abiertas = new Set();

/* --- botón "atrás" del móvil ---
   El panel es su propia página. Sin esto, la flecha del móvil abandonaba el
   panel (y a veces cerraba la app). Se deja una entrada propia en el historial:
   mientras haya algo abierto, "atrás" cierra lo último; si no hay nada, vuelve
   al juego en vez de salir del panel. */
let capaPropia = false;

function asegurarCapa() {
  if (capaPropia) return;
  try { history.pushState({ panel: true }, ""); capaPropia = true; } catch (e) { /* antiguo */ }
}

function cerrarUltimo() {
  if (!$("#dialogo").hidden) { $("#dialogo").hidden = true; return; }
  const ventanas = document.querySelectorAll(".ventana");
  if (ventanas.length) cerrarVentana(ventanas[ventanas.length - 1].id.replace("ventana-", ""));
}

window.addEventListener("popstate", () => {
  capaPropia = false;
  const hayAlgo = !$("#dialogo").hidden || document.querySelectorAll(".ventana").length;
  if (hayAlgo) { cerrarUltimo(); asegurarCapa(); return; }
  location.href = "/";
});

function abrirVentana(clave) {
  const cfg = VENTANAS[clave];
  if (!cfg) return;
  if (abiertas.has(clave)) {
    const v = document.getElementById("ventana-" + clave);
    if (v) {
      v.classList.add("ventana--foco");
      setTimeout(() => v.classList.remove("ventana--foco"), 700);
    }
    return;
  }
  abiertas.add(clave);
  asegurarCapa();
  const v = document.createElement("section");
  v.className = "ventana";
  v.id = "ventana-" + clave;
  v.innerHTML = `
    <header class="ventana__barra">
      <h2 class="ventana__titulo">${cfg.titulo}</h2>
      <button class="ventana__cerrar" aria-label="Cerrar" data-cerrar-ventana="${clave}">×</button>
    </header>
    <div class="ventana__cuerpo" id="cuerpo-${clave}">
      <p class="vacio">Cargando…</p>
    </div>`;
  $("#ventanas").appendChild(v);
  v.querySelector("[data-cerrar-ventana]").onclick = () => cerrarVentana(clave);
  Promise.resolve()
    .then(() => cfg.cargar())
    .then(() => { engancharBusqueda(); engancharChat(); })
    .catch((err) => avisar(err.message, "error"));
}

function cerrarVentana(clave) {
  abiertas.delete(clave);
  const v = document.getElementById("ventana-" + clave);
  if (v) v.remove();
}

/* --- salas en vivo (admin) --- */

// El admin ve cada sala por dentro: quién juega, con qué cartones y qué bolas.
let salaVivaActual = "";

async function cargarSalasAdmin() {
  const caja = $("#cuerpo-salas");
  if (!caja) return;
  const res = await get("/api/admin/salas");
  if (!res.salas.length) { caja.innerHTML = '<p class="vacio">No hay salas.</p>'; return; }
  caja.innerHTML = `
    <div class="tabla-scroll"><table class="tabla">
      <thead><tr><th>Sala</th><th>Dueño</th><th>Modo</th><th>Juego</th><th>Cartón</th>
        <th>Cartones</th><th>Fecha</th><th>Estado</th><th></th></tr></thead>
      <tbody>${res.salas.map((s) => `
        <tr>
          <td><strong>${s.nombre}</strong>${s.es_evento ? ' <span class="etiqueta-rol">evento</span>' : ""}</td>
          <td>${s.dueno || "La casa"}</td>
          <td>${s.modo}</td>
          <td>${s.tipo_juego_texto || "—"}</td>
          <td>${s.precio_texto}</td>
          <td>${s.cupo_cartones > 0 ? s.cupo_cartones : "sin tope"}</td>
          <td>${s.fecha_partida || "—"}</td>
          <td><span class="etiqueta etiqueta--${s.activa ? "acreditado" : "rechazado"}">${
            s.activa ? "abierta" : "cerrada"}</span></td>
          <td class="acciones-celda">
            <button class="boton boton--fantasma boton--mini" data-ver="${s.id}">Ver sala</button>
            ${s.dueno ? "" : `<button class="boton boton--fantasma boton--mini" data-editar="${s.id}">Editar</button>`}
            ${s.activa && s.dueno
              ? `<button class="boton boton--fantasma boton--mini" data-cerrar-sala="${s.id}">Cerrar</button>`
              : ""}
          </td>
        </tr>`).join("")}</tbody>
    </table></div>
    <div id="sala-viva"></div>`;
  caja.querySelectorAll("[data-ver]").forEach((b) => (b.onclick = () => verSala(b.dataset.ver)));
  caja.querySelectorAll("[data-editar]").forEach((b) =>
    (b.onclick = () => editarSala(res.salas.find((s) => s.id === b.dataset.editar))));
  caja.querySelectorAll("[data-cerrar-sala]").forEach((b) =>
    (b.onclick = async () => {
      if (!confirm("¿Cerrar esta sala de jugador?")) return;
      try {
        await post("/api/sala/cerrar", { sala: b.dataset.cerrarSala });
        avisar("Sala cerrada.", "bien");
        cargarSalasAdmin();
      } catch (err) { avisar(err.message, "error"); }
    }));
}

async function verSala(salaId) {
  salaVivaActual = salaId;
  await pintarSalaViva();
}

// Cada sala se ajusta desde el panel: precio, tipo de juego, cartones a la venta
// y fecha. Así no hay que tocar el repositorio para cambiar nada.
let TIPOS_JUEGO = [];
async function tiposDeJuego() {
  if (TIPOS_JUEGO.length) return TIPOS_JUEGO;
  try {
    const c = await get("/api/config");
    TIPOS_JUEGO = c.tipos_juego || [];
  } catch (err) { TIPOS_JUEGO = []; }
  return TIPOS_JUEGO;
}

async function editarSala(sala) {
  if (!sala) return;
  const tipos = await tiposDeJuego();
  const opciones = tipos.map((t) =>
    `<option value="${t.id}" ${t.id === sala.tipo_juego ? "selected" : ""}>${t.nombre}</option>`).join("");
  abrirDialogo(`
    <h2>Editar sala</h2>
    <p style="color:var(--gris);font-size:.9rem">${sala.nombre}</p>
    <form id="form-sala">
      <label>Nombre<input type="text" name="nombre" value="${sala.nombre}" required maxlength="60"></label>
      <label>Precio del cartón ($)
        <input type="text" name="precio" value="${sala.precio_texto.replace("$ ", "")}" required>
      </label>
      <label>Tipo de juego<select name="tipo_juego">${opciones}</select></label>
      <label>Cartones a la venta (0 = sin tope)
        <input type="number" name="cupo_cartones" min="0" step="1" value="${sala.cupo_cartones || 0}">
      </label>
      <label>Cartones por jugador (0 = sin tope)
        <input type="number" name="max_cartones" min="0" step="1" value="${sala.max_cartones || 0}">
      </label>
      <label>Fecha de la partida
        <input type="text" name="fecha_partida" maxlength="60" placeholder="Ej.: hoy 8:00 pm"
               value="${sala.fecha_partida || ""}">
      </label>
      <button class="boton boton--principal" type="submit">Guardar</button>
    </form>
    <p class="ayuda">Los jugadores ven el cambio enseguida. Las partidas ya empezadas
       mantienen el precio y el tipo de juego con el que se abrieron.</p>`);
  $("#form-sala").onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      const res = await post("/api/admin/sala/editar", {
        sala: sala.id, nombre: d.nombre, precio: d.precio,
        tipo_juego: d.tipo_juego, cupo_cartones: d.cupo_cartones,
        max_cartones: d.max_cartones, fecha_partida: d.fecha_partida,
      });
      $("#dialogo").hidden = true;
      avisar(res.mensaje, "bien");
      cargarSalasAdmin();
    } catch (err) { avisar(err.message, "error"); }
  };
}

async function pintarSalaViva() {
  const caja = $("#sala-viva");
  if (!caja || !salaVivaActual) return;
  try {
    const v = await get("/api/admin/sala?sala=" + encodeURIComponent(salaVivaActual));
    const mesas = v.jugadores.map((j) => `
      <div class="mesa-jugador">
        <div class="mesa-jugador__cabeza">
          <strong>${j.correo}</strong>
          <span class="pastilla pastilla--suave">${j.cartones} cartón(es)</span>
        </div>
        <div class="mesa-jugador__cartones">${j.detalle.map(cartonHtml).join("")}</div>
        ${j.premios.length
          ? `<p class="mesa-jugador__premio">Ganó: ${j.premios.map((p) => p.nombre || "premio").join(", ")}</p>`
          : ""}
      </div>`).join("") || '<p class="vacio">Nadie ha comprado cartón todavía.</p>';
    caja.innerHTML = `
      <div class="evento__cabecera" style="margin:1.2rem 0 .6rem">
        <h3 class="evento__titulo">${v.sala.nombre}</h3>
        <span class="evento__aforo">${v.jugadores.length} jugador(es) · ${v.cartones} cartón(es)
          · Bote ${v.bote_texto}</span>
      </div>
      <p class="ayuda">Bolas sacadas: ${v.bolas_sacadas.length
        ? v.bolas_sacadas.join(" · ") : "ninguna todavía"}</p>
      <div class="mesas-jugadores">${mesas}</div>`;
  } catch (err) { caja.innerHTML = `<p class="vacio">${err.message}</p>`; }
}

function cartonHtml(c) {
  const marcados = new Set(c.marcados);
  const filas = c.numeros.map((fila, f) => `<tr>${fila.map((n, col) => {
    const libre = f === 2 && col === 2;
    const marca = libre || marcados.has(`${f}-${col}`);
    return `<td class="${marca ? "carton-mini__marcado" : ""}">${libre ? "★" : n}</td>`;
  }).join("")}</tr>`).join("");
  return `<table class="carton-mini"><tbody>${filas}</tbody></table>`;
}

/* --- arranque --- */

const ORDEN_VENTANAS = ["resumen", "glenis", "torneos", "depositos", "retiros", "jugadores",
                        "partidas", "salas", "cobros", "ganancias", "referidos", "movimientos"];

function pintarLanzadera() {
  const caja = $("#lanzadera");
  if (!caja) return;
  caja.innerHTML = ORDEN_VENTANAS.map((k) =>
    `<button class="lanzadera__boton" data-abrir="${k}">${VENTANAS[k].titulo}</button>`).join("");
  caja.querySelectorAll("[data-abrir]").forEach((b) =>
    (b.onclick = () => abrirVentana(b.dataset.abrir)));
}

document.querySelectorAll("#nav-admin [data-ventana]").forEach((b) =>
  (b.onclick = () => abrirVentana(b.dataset.ventana)));

async function cargarTodo() {
  if (!token) { abrirAcceso(); return; }
  try {
    const s = await get("/api/saldo");
    if (!s.admin) throw new Error("Esa cuenta no es de administración.");
    pintarSesion(localStorage.getItem("bp777_correo"));
    pintarLanzadera();
    abrirVentana("resumen");
  } catch (err) {
    avisar(err.message, "error");
    localStorage.removeItem(CLAVE_TOKEN);
    abrirAcceso();
  }
}

function engancharBusqueda() {
  const caja = $("#buscar-jugador");
  if (caja && !caja.dataset.listo) {
    caja.dataset.listo = "1";
    caja.oninput = pintarJugadores;
  }
}

function engancharChat() {
  const form = $("#chat-form");
  if (form && !form.dataset.listo) {
    form.dataset.listo = "1";
    form.onsubmit = (e) => { e.preventDefault(); hablarConGlenis($("#chat-texto").value); };
    document.querySelectorAll("[data-sugerencia]").forEach((b) =>
      (b.onclick = () => hablarConGlenis(b.dataset.sugerencia)));
  }
}

cargarTodo();
setInterval(() => {
  if (!token) return;
  if (abiertas.has("resumen")) cargarResumen();
  if (abiertas.has("retiros")) cargarRetiros();
  if (abiertas.has("salas") && salaVivaActual) pintarSalaViva();
}, 15000);
