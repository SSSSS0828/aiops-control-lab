// 轻量 SVG 趋势线直接消费受控历史样本，不引入大型图表库。
import type { MetricHistoryPoint } from "./types";

export function MetricSparkline({ points }: { points: MetricHistoryPoint[] }) {
  if (points.length < 2) return <div className="sparkline-empty">等待历史样本</div>;
  const values = points.map((item) => item.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = Math.max(maximum - minimum, 1);
  const coordinates = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 100;
      const y = 36 - ((value - minimum) / span) * 32;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg aria-label="最近三十分钟指标趋势" className="metric-sparkline" viewBox="0 0 100 40">
      <polyline fill="none" points={coordinates} stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
