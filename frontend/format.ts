export function formatMetric(value: number, metric?: string) {
  const fraction = [
    "accuracy",
    "auc",
    "auroc",
    "f1",
    "f1_macro",
    "f1_micro",
    "precision",
    "recall",
  ].includes(metric || "");
  return fraction
    ? `${(value * 100).toFixed(2)}%`
    : value.toLocaleString(undefined, { maximumFractionDigits: 5 });
}
