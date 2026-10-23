import { useEffect, useState } from "react";
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from "recharts";
import { api } from "./api";

const MW = (n) => (n == null ? "–" : `${Math.round(n).toLocaleString("en-GB")} MW`);
const fmt = (iso, opts) => new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", ...opts }).format(new Date(iso));
const hhmm = (iso) => fmt(iso, { hour: "2-digit", minute: "2-digit" });
const longTime = (iso) => fmt(iso, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const pad = (n) => String(n).padStart(2, "0");

function useApi(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((e) => !cancelled && setState({ data: null, error: e.message, loading: false }));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

function Card({ label, value, hint, title }) {
  return (
    <div className="card" title={title}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      <div className="hint">{hint}</div>
    </div>
  );
}

function Status({ s }) {
  if (s.loading) return <div className="panel">Loading…</div>;
  if (s.error) return <div className="panel error">Could not load data: {s.error}</div>;
  return null;
}

/* ---------- View 1: what the buyer saw at decision time ---------- */
function DecisionView({ config, hour, minute }) {
  const [date, setDate] = useState(config.delivery_dates[8]);
  const [showActual, setShowActual] = useState(false);
  const s = useApi(() => api.day(date, hour, minute), [date, hour, minute]);
  const d = s.data;
  const points = d?.points.map((p) => ({
    time: hhmm(p.startTime),
    Forecast: p.forecast,
    "Actual (known only after delivery)": showActual ? p.actual : null,
  }));
  return (
    <>
      <div className="panel controls">
        <label>Delivery day you are buying for
          <select value={date} onChange={(e) => setDate(e.target.value)}>
            {config.delivery_dates.map((x) => <option key={x}>{x}</option>)}
          </select>
        </label>
        <label style={{ flexDirection: "row", alignItems: "center", color: "inherit" }}>
          <input type="checkbox" checked={showActual} onChange={(e) => setShowActual(e.target.checked)} />
          Reveal what actually happened
        </label>
      </div>
      <Status s={s} />
      {d && (
        <>
          <div className="cards">
            <Card label="Decision deadline" value={longTime(d.decision_cutoff_utc)} hint="London time, day before delivery" />
            <Card label="Forecast you could use" value={longTime(d.forecast_published_to)} hint="Latest forecast published before the deadline" />
            <Card label="Expected wind energy" value={`${Math.round(d.forecast_total_mwh).toLocaleString("en-GB")} MWh`} hint="Forecast total for the delivery day" />
          </div>
          <div className="panel">
            <h2>Wind forecast for {d.delivery_date} (MW, half-hourly)</h2>
            <ResponsiveContainer width="100%" height={340}>
              <LineChart data={points}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" interval={3} />
                <YAxis tickFormatter={(v) => v.toLocaleString("en-GB")} />
                <Tooltip formatter={(v) => MW(v)} />
                <Legend />
                <Line type="stepAfter" dataKey="Forecast" stroke="#2563eb" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="Actual (known only after delivery)" stroke="#ea580c" dot={false} strokeWidth={2} connectNulls />
              </LineChart>
            </ResponsiveContainer>
            <div className="note">
              Power to buy from other sources ≈ expected demand minus this wind forecast. Forecasts published after the deadline are ignored because the buyer could not have used them.
            </div>
          </div>
          {showActual && (
            <div className="cards">
              <Card label="Average miss that day" value={MW(d.metrics.mae_mw)} hint="Mean absolute error" />
              <Card label="Bias that day" value={MW(d.metrics.bias_mw)} hint="Positive = forecast too high" />
              <Card label="Worst-5% miss" value={MW(d.metrics.p95_abs_error_mw)} hint="95th percentile of absolute error" />
            </div>
          )}
        </>
      )}
    </>
  );
}

/* ---------- View 2: how accurate were the forecasts? ---------- */
function AccuracyView({ hour, minute }) {
  const s = useApi(() => api.metrics(hour, minute), [hour, minute]);
  if (s.loading || s.error) return <Status s={s} />;
  const m = s.data.summary;
  return (
    <>
      <div className="cards">
        <Card label="MAE – average miss" value={MW(m.mae_mw)} hint="Typical size of the error" title="Mean absolute error" />
        <Card label="RMSE" value={MW(m.rmse_mw)} hint="Like MAE but penalises big misses" title="Root mean squared error" />
        <Card label="Bias" value={MW(m.bias_mw)} hint={m.bias_mw > 0 ? "Forecasts too HIGH on average" : "Forecasts too LOW on average"} title="Mean of (forecast − actual)" />
        <Card label="MAPE" value={`${m.mape_pct.toFixed(1)}%`} hint="Error as % of actual wind" />
      </div>
      <div className="panel">
        <h2>Error by delivery day (MW)</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={s.data.by_day}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="delivery_date" tickFormatter={(v) => v.slice(5)} interval={2} />
            <YAxis />
            <Tooltip formatter={(v) => MW(v)} />
            <Legend />
            <Bar dataKey="mae_mw" name="Average miss (MAE)" fill="#2563eb" />
            <Bar dataKey="bias_mw" name="Bias (+ = forecast too high)" fill="#ea580c" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="panel">
        <h2>Average miss by hour of day (MW)</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={s.data.by_hour}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="hour" tickFormatter={(h) => `${pad(h)}:00`} />
            <YAxis />
            <Tooltip formatter={(v) => MW(v)} labelFormatter={(h) => `${pad(h)}:00 London`} />
            <Bar dataKey="mae_mw" name="MAE" fill="#2563eb" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

/* ---------- View 3: risk and recommended buffer ---------- */
function RiskView({ hour, minute }) {
  const m = useApi(() => api.metrics(hour, minute), [hour, minute]);
  const dist = useApi(() => api.distribution(hour, minute), [hour, minute]);
  const hz = useApi(() => api.horizon(), []);
  if (m.loading || m.error) return <Status s={m} />;
  const sum = m.data.summary;
  return (
    <>
      <div className="callout">
        <b>What this means for buying.</b> On average the forecast was <b>{MW(Math.abs(sum.bias_mw))}</b>{" "}
        {sum.bias_mw > 0 ? "higher" : "lower"} than the wind that actually arrived. In 9 of 10 half-hours the
        forecast was too high by no more than <b>{MW(sum.buffer_p90_mw)}</b>; in 19 of 20 by no more than{" "}
        <b>{MW(sum.buffer_p95_mw)}</b>. Holding a buffer of that size would have covered those shortfalls.
      </div>
      <div className="cards">
        <Card label="Buffer for 90% cover" value={MW(sum.buffer_p90_mw)} hint="Extra power to cover over-forecasts 90% of the time" />
        <Card label="Buffer for 95% cover" value={MW(sum.buffer_p95_mw)} hint="Extra power to cover over-forecasts 95% of the time" />
        <Card label="95th pct. absolute miss" value={MW(sum.p95_abs_error_mw)} hint="Misses in either direction" />
      </div>
      <div className="panel">
        <h2>How often is the forecast wrong, and by how much?</h2>
        {dist.data && (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={dist.data.bins}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="from" tickFormatter={(v) => v.toLocaleString("en-GB")} interval={1} />
              <YAxis allowDecimals={false} />
              <Tooltip labelFormatter={(v) => `Error from ${v.toLocaleString("en-GB")} MW`} formatter={(v) => [`${v} half-hours`, "Count"]} />
              <Bar dataKey="count">
                {dist.data.bins.map((b) => (
                  <Cell key={b.from} fill={b.from >= 0 ? "#ea580c" : "#16a34a"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
        <div className="note">Orange = forecast too high (wind lower than expected, risk of a shortfall). Green = forecast too low (surplus).</div>
      </div>
      <div className="panel">
        <h2>Forecasts get better closer to delivery</h2>
        {hz.data && (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={hz.data.buckets.map((b) => ({ ...b, label: `${b.bucket_start}–${b.bucket_end}h` }))}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" />
              <YAxis />
              <Tooltip formatter={(v) => MW(v)} />
              <Bar dataKey="mae_mw" name="Average miss (MAE)" fill="#2563eb" />
            </BarChart>
          </ResponsiveContainer>
        )}
        <div className="note">
          Horizontal axis = how many hours before the delivery time the forecast was published. A day-ahead buyer has to
          decide earlier, so must use the older, less accurate forecasts on the right.
        </div>
      </div>
    </>
  );
}

/* ---------- App shell ---------- */
export default function App() {
  const cfg = useApi(() => api.config(), []);
  const [tab, setTab] = useState("decision");
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);

  return (
    <div className="wrap">
      <h1>UK Wind Forecast Dashboard</h1>
      <p className="sub">Day-ahead buying: the forecast available at decision time, and how far off it typically is (January 2026 decisions, national wind, Elexon data).</p>
      <Status s={cfg} />
      {cfg.data && (
        <>
          <div className="panel controls">
            <label>Decision deadline, hour (London time, day before)
              <input type="number" min="0" max="23" value={hour}
                onChange={(e) => setHour(Math.min(23, Math.max(0, Number(e.target.value) || 0)))} />
            </label>
            <label>Minute
              <select value={minute} onChange={(e) => setMinute(Number(e.target.value))}>
                {[0, 15, 30, 45].map((x) => <option key={x} value={x}>{pad(x)}</option>)}
              </select>
            </label>
            <div className="note" style={{ margin: 0 }}>
              Forecasts are published at {cfg.data.typical_publish_times_utc.join(", ")} (UTC). Change the deadline to see how it affects the forecast you can use.
            </div>
          </div>
          <div className="tabs">
            {[["decision", "1. Decision view"], ["accuracy", "2. Forecast accuracy"], ["risk", "3. Risk & buffer"]].map(([k, label]) => (
              <button key={k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>{label}</button>
            ))}
          </div>
          {tab === "decision" && <DecisionView config={cfg.data} hour={hour} minute={minute} />}
          {tab === "accuracy" && <AccuracyView hour={hour} minute={minute} />}
          {tab === "risk" && <RiskView hour={hour} minute={minute} />}
        </>
      )}
    </div>
  );
}
