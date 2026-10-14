/**
 * The JS mirror of the palette in index.css.
 *
 * SVG charts and the handful of JS-computed styles cannot read CSS custom
 * properties reliably, so they read from here instead. It is the same closed
 * set: one accent, five neutrals, three status hues. Nothing in this file is a
 * one-off — every badge, bar, pill and chart pulls from these values, so a
 * concept (positive sentiment, high severity, a category) looks the same on
 * every screen.
 *
 * If index.css changes, change this file with it.
 */

export const palette = {
  accent: '#1e3a8a',
  accentStrong: '#172554',
  ink: '#18181b',
  muted: '#71717a',
  line: '#e4e4e7',
  surface: '#ffffff',
  canvas: '#fafafa',
  success: '#047857',
  warning: '#b45309',
  danger: '#b91c1c',
};

/** The accent, as a series colour for charts. */
export const accent = { line: palette.accent, strong: palette.accentStrong };

/** Same colour at low alpha — the tinted background behind a label. */
export function tint(hex, alpha = 0.08) {
  const value = parseInt(hex.slice(1), 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

export const sentiment = {
  positive: { line: palette.success, soft: tint(palette.success, 0.08), border: tint(palette.success, 0.26) },
  neutral: { line: palette.warning, soft: tint(palette.warning, 0.09), border: tint(palette.warning, 0.28) },
  negative: { line: palette.danger, soft: tint(palette.danger, 0.07), border: tint(palette.danger, 0.26) },
};

export const severity = {
  high: { line: palette.danger, soft: tint(palette.danger, 0.07) },
  medium: { line: palette.warning, soft: tint(palette.warning, 0.09) },
  low: { line: palette.muted, soft: tint(palette.muted, 0.08) },
};

export const demand = {
  high: { line: palette.accent, soft: tint(palette.accent, 0.08) },
  medium: { line: palette.warning, soft: tint(palette.warning, 0.09) },
  low: { line: palette.muted, soft: tint(palette.muted, 0.08) },
};

/**
 * The one place more than three hues are genuinely needed: telling feedback
 * categories apart in a pie or bar chart. A closed, documented ramp — never
 * used for interface chrome, only for data series.
 */
export const categoryColors = {
  feature_request: '#2563eb',
  bug_report: '#dc2626',
  performance_issue: '#b45309',
  ui_ux: '#7c3aed',
  general_feedback: '#047857',
  customer_support: '#db2777',
  integration: '#0e7490',
  security: '#4f46e5',
};

export const defaultCategoryPalette = [
  '#4f46e5',
  '#0e7490',
  '#2563eb',
  '#b45309',
  '#047857',
  '#db2777',
  '#7c3aed',
  '#dc2626',
  '#0891b2',
  '#4d7c0f',
];

/** Stable colour for a feedback category, tolerating free-form labels from the backend. */
export function getCategoryColor(category, idx = 0) {
  const fallback = defaultCategoryPalette[idx % defaultCategoryPalette.length];
  const normalized = (category || '').toLowerCase().trim().replace(/[\s-]+/g, '_');
  if (!normalized) return fallback;
  if (categoryColors[normalized]) return categoryColors[normalized];

  const key = Object.keys(categoryColors).find((k) => normalized.includes(k.split('_')[0]));
  return key ? categoryColors[key] : fallback;
}
