// Reconnecting WebSocket client for /ws with exponential backoff + jitter and a keep-alive ping.
// Usage: const feed = connectEvents({ quality: (data) => ..., check_result: (data) => ... }, onStatus);

export function connectEvents(handlers = {}, onStatus = () => {}) {
  let socket = null;
  let attempt = 0;
  let pingTimer = null;
  let closed = false;

  const url = () => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

  function schedule() {
    if (closed) return;
    const delay = Math.min(15000, 500 * 2 ** attempt) + Math.random() * 400;
    attempt += 1;
    setTimeout(open, delay);
  }

  function open() {
    if (closed) return;
    onStatus("connecting");
    try {
      socket = new WebSocket(url());
    } catch (e) {
      schedule();
      return;
    }
    socket.onopen = () => {
      attempt = 0;
      onStatus("open");
      clearInterval(pingTimer);
      pingTimer = setInterval(() => { if (socket && socket.readyState === 1) socket.send("ping"); }, 20000);
    };
    socket.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch (err) { return; }
      const fn = handlers[msg.type];
      if (fn) {
        try { fn(msg.data, msg); } catch (err) { console.error("event handler failed", msg.type, err); }
      }
      if (handlers["*"]) handlers["*"](msg.data, msg);
    };
    socket.onclose = () => {
      clearInterval(pingTimer);
      onStatus("closed");
      schedule();
    };
    socket.onerror = () => { try { socket.close(); } catch (e) { /* ignore */ } };
  }

  open();
  return {
    close() { closed = true; clearInterval(pingTimer); if (socket) socket.close(); },
  };
}
