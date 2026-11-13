// WebSocket link to the herd daemon: RPC calls, events, pane output. Reconnects automatically.

function readToken() {
  const params = new URLSearchParams(location.search);
  let token = params.get("token");
  try {
    if (token) sessionStorage.setItem("herd-token", token);
    else token = sessionStorage.getItem("herd-token");
  } catch { /* storage may be blocked; keep URL token */ }
  if (params.has("token")) history.replaceState(null, "", location.pathname);
  return token || "";
}

export class Connection {
  constructor() {
    this.token = readToken();
    this.nextId = 1;
    this.pending = new Map();
    this.eventHandlers = new Set();
    this.outputHandlers = new Map(); // pane id -> fn(data, isReplay)
    this.attached = new Set();
    this.ws = null;
    this.connected = false;
    this.onConnection = () => {};
  }

  connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(this.token)}&label=ui`);
    this.ws = ws;
    ws.onopen = () => {
      this.connected = true;
      this.onConnection(true);
      for (const pane of this.attached) this.send({ t: "attach", pane });
    };
    ws.onmessage = (ev) => this.dispatch(JSON.parse(ev.data));
    ws.onclose = () => {
      this.connected = false;
      this.onConnection(false);
      for (const [, p] of this.pending) p.reject(new Error("disconnected"));
      this.pending.clear();
      setTimeout(() => this.connect(), 1500);
    };
  }

  dispatch(msg) {
    if (msg.t === "res") {
      const waiter = this.pending.get(msg.id);
      if (!waiter) return;
      this.pending.delete(msg.id);
      if (msg.error) waiter.reject(Object.assign(new Error(msg.error.message), { code: msg.error.code }));
      else waiter.resolve(msg.result);
    } else if (msg.t === "ev") {
      for (const fn of this.eventHandlers) fn(msg.name, msg.data);
    } else if (msg.t === "out" || msg.t === "replay") {
      const fn = this.outputHandlers.get(msg.pane);
      if (fn) fn(msg.data, msg.t === "replay");
    }
  }

  send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  rpc(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      if (!this.connected) return reject(new Error("not connected to herd-server"));
      this.pending.set(id, { resolve, reject });
      this.send({ t: "rpc", id, method, params });
    });
  }

  onEvent(fn) { this.eventHandlers.add(fn); return () => this.eventHandlers.delete(fn); }

  attach(pane, onData) {
    this.outputHandlers.set(pane, onData);
    if (!this.attached.has(pane)) { this.attached.add(pane); this.send({ t: "attach", pane }); }
  }

  detach(pane) {
    this.outputHandlers.delete(pane);
    if (this.attached.delete(pane)) this.send({ t: "detach", pane });
  }

  input(pane, data) { this.send({ t: "in", pane, data }); }

  /** After a server-side overflow: ask again for every pane (the daemon replays their output). */
  reattachAll() { for (const pane of this.attached) this.send({ t: "attach", pane }); }
}

export const conn = new Connection();
