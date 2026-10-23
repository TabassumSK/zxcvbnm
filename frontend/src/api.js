// All backend calls live here. In production set VITE_API_URL to the backend address.
const BASE = import.meta.env.VITE_API_URL || "";

async function get(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null)
  ).toString();
  const res = await fetch(`${BASE}/api/${path}${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`Request failed (${res.status}): ${await res.text()}`);
  return res.json();
}

export const api = {
  config: () => get("config"),
  day: (date, h, m) => get("day", { date, cutoff_hour: h, cutoff_minute: m }),
  metrics: (h, m) => get("metrics", { cutoff_hour: h, cutoff_minute: m }),
  distribution: (h, m) => get("error-distribution", { cutoff_hour: h, cutoff_minute: m, bin_width: 500 }),
  horizon: () => get("horizon", { bucket_hours: 6 }),
};