// TA PIN gate for /ta and /labs/editor.
import { $, api } from "./ui.js";

$("#pin-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { ok } = await api("/api/ta/login", { method: "POST", json: { pin: $("#pin").value } });
  if (ok) location.reload();
  else {
    $("#pin-error").hidden = false;
    $("#pin").select();
  }
});
