import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";
import type { Run } from "./types";
import { humanize } from "./types";
export default function RunChart({ runs }: { runs: Run[] }) {
  const complete = runs.filter(
    (r) => r.status === "completed" && r.output.metrics,
  );
  const metric = [
    "accuracy",
    "auc",
    "f1_macro",
    "r2",
    "rmse",
    ...Object.keys(complete[0]?.output.metrics || {}),
  ].find(
    (key) =>
      complete.length > 0 &&
      complete.every((r) => Number.isFinite(r.output.metrics?.[key])),
  );
  if (!metric)
    return complete.length ? (
      <p className="panel-description">
        These runs have no common measured metric. Inspect their individual
        results.
      </p>
    ) : null;
  const data = complete.map((r) => ({
    name: humanize(r.manifest.variant),
    value: r.output.metrics![metric],
    color: r.manifest.variant === "baseline" ? "#5cc8ff" : "#70f3c2",
  }));
  if (!data.length) return null;
  return (
    <div
      className="run-chart"
      role="img"
      aria-label={data
        .map((x) => `${x.name}, ${metric}: ${x.value.toFixed(4)}`)
        .join("; ")}
    >
      <ResponsiveContainer width="100%" height={230}>
        <BarChart
          data={data}
          margin={{ left: -15, right: 10, top: 15, bottom: 10 }}
        >
          <CartesianGrid stroke="#1a2b35" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: "#9aaab8", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#6f8494", fontSize: 11 }}
            domain={metric === "r2" ? ["auto", "auto"] : [0, "auto"]}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "#15252e" }}
            contentStyle={{
              background: "#101a24",
              border: "1px solid #2a414a",
              borderRadius: 10,
              color: "#edf3f6",
            }}
          />
          <Bar dataKey="value" name={metric} radius={[5, 5, 0, 0]} barSize={60}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
