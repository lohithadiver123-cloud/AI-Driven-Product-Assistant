/**
 * Monochrome line icons, drawn on a 24px grid and inheriting `currentColor`.
 *
 * Usage: <Icon name="search" /> · <Icon name="star" fill /> · <Icon name="plus" size={14} />
 *
 * One component with a name map keeps the set consistent (same stroke width,
 * caps and joins) and easy to extend, instead of a file per glyph.
 */

const PATHS = {
  // --- actions ---------------------------------------------------------
  plus: <><path d="M12 5v14" /><path d="M5 12h14" /></>,
  minus: <path d="M5 12h14" />,
  x: <><path d="M18 6 6 18" /><path d="m6 6 12 12" /></>,
  check: <path d="M20 6 9 17l-5-5" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20.5 20.5-4-4" /></>,
  trash: <><path d="M4 7h16" /><path d="M9 7V5h6v2" /><path d="M6.5 7l.9 13h9.2l.9-13" /></>,
  pencil: <><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z" /><path d="m13.5 6.5 3 3" /></>,
  save: <><path d="M5 3h11l3 3v15H5z" /><path d="M8 3v6h7V3" /><path d="M8 21v-6h8v6" /></>,
  refresh: <><path d="M20 11a8 8 0 1 0-2.3 5.6" /><path d="M20 5v6h-6" /></>,
  download: <><path d="M12 3v12" /><path d="m7.5 10.5 4.5 4.5 4.5-4.5" /><path d="M4 20h16" /></>,
  external: <><path d="M14 4h6v6" /><path d="M20 4 11 13" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></>,

  // --- navigation / structure -----------------------------------------
  arrowRight: <><path d="M4 12h15" /><path d="m13 6 6 6-6 6" /></>,
  chevronRight: <path d="m9 5 7 7-7 7" />,
  chevronDown: <path d="m5 9 7 7 7-7" />,
  chevronUp: <path d="m19 15-7-7-7 7" />,
  arrowLeft: <><path d="M20 12H5" /><path d="m11 18-6-6 6-6" /></>,
  collapse: <><path d="m6 9 6 6 6-6" /><path d="M4 4h16" /></>,
  table: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18" /><path d="M3 15h18" /><path d="M9 10v10" /></>,
  columns: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /><path d="M15 4v16" /></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  sliders: <><path d="M4 6h10" /><path d="M18 6h2" /><path d="M4 12h4" /><path d="M12 12h8" /><path d="M4 18h12" /><path d="M20 18h0" /><circle cx="16" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></>,
  key: <><circle cx="8" cy="12" r="3.5" /><path d="M11.5 12H21" /><path d="M18 12v3" /></>,
  lock: <><rect x="4.5" y="10" width="15" height="10" rx="2" /><path d="M8 10V7.5a4 4 0 0 1 8 0V10" /></>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3.5 7 8.5 6 8.5-6" /></>,
  userPlus: <><circle cx="10" cy="8" r="3.2" /><path d="M4 20a6 6 0 0 1 12 0" /><path d="M18 8v6" /><path d="M15 11h6" /></>,
  logOut: <><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" /><path d="M10 8l-4 4 4 4" /><path d="M6 12h10" /></>,
  play: <path d="M7 4.5 19 12 7 19.5z" />,
  checkCircle: <><circle cx="12" cy="12" r="9" /><path d="m8.5 12.5 2.5 2.5 4.5-5" /></>,
  xCircle: <><circle cx="12" cy="12" r="9" /><path d="m9 9 6 6" /><path d="m15 9-6 6" /></>,
  shield: <><path d="M12 3l7 3v6c0 4.2-2.9 7.6-7 9-4.1-1.4-7-4.8-7-9V6z" /><path d="m9 12 2 2 4-4" /></>,
  code: <><path d="m9 8-4 4 4 4" /><path d="m15 8 4 4-4 4" /></>,
  menu: <><path d="M4 7h16" /><path d="M4 12h16" /><path d="M4 17h16" /></>,
  server: <><rect x="3" y="4" width="18" height="7" rx="2" /><rect x="3" y="13" width="18" height="7" rx="2" /><path d="M7 7.5h.01" /><path d="M7 16.5h.01" /></>,
  hash: <><path d="M5 9h14" /><path d="M5 15h14" /><path d="M10 4 8 20" /><path d="M16 4l-2 16" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18" /><path d="M8 3v4" /><path d="M16 3v4" /></>,
  tag: <><path d="M3.5 11.5 11 4h8v8l-7.5 7.5a2 2 0 0 1-2.8 0L3.5 14.3a2 2 0 0 1 0-2.8Z" /><path d="M15.5 8.5h.01" /></>,
  layout: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18" /><path d="M9 9v12" /></>,
  inbox: <><path d="M3 12h5l1.5 3h5L16 12h5" /><path d="M4.5 5h15l1.5 7v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6z" /></>,

  // --- domain ----------------------------------------------------------
  file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /><path d="M9 13h6" /><path d="M9 17h4" /></>,
  clipboard: <><rect x="8" y="3" width="8" height="4" rx="1" /><path d="M16 5h2a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2" /><path d="M9 12h6" /><path d="M9 16h6" /></>,
  target: <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><circle cx="12" cy="12" r="1.2" /></>,
  scale: <><path d="M12 4v16" /><path d="M6 7h12" /><path d="M8.5 7 5.5 14h6z" /><path d="M15.5 7l-3 7h6z" /></>,
  barChart: <><path d="M4 20V4" /><path d="M4 20h16" /><path d="M9 20v-6" /><path d="M14 20V9" /><path d="M19 20v-9" /></>,
  zap: <path d="M13.5 3 5.5 13.5H11L10.5 21l8-10.5H13z" />,
  bulb: <><path d="M9.5 18h5" /><path d="M10 21h4" /><path d="M12 3a5.5 5.5 0 0 0-3.2 9.9V15h6.4v-2.1A5.5 5.5 0 0 0 12 3Z" /></>,
  flask: <><path d="M9 3h6" /><path d="M10 3v6.5L5.5 17A2 2 0 0 0 7.2 20h9.6a2 2 0 0 0 1.7-3L14 9.5V3" /><path d="M7.5 14h9" /></>,
  trendingUp: <><path d="M3 17l6-6 4 4 7-7" /><path d="M14 8h6v6" /></>,
  alert: <><path d="M12 3.5 21 19H3z" /><path d="M12 10v4" /><path d="M12 17h.01" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 8h.01" /></>,
  user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></>,
  users: <><circle cx="9" cy="8" r="3.2" /><path d="M3 20a6 6 0 0 1 12 0" /><path d="M16.5 5.2a3.2 3.2 0 0 1 0 5.6" /><path d="M18 20a6 6 0 0 0-1.5-4" /></>,
  chat: <><path d="M20 12a7.5 7.5 0 0 1-11 6.7L4.5 20l1.3-4.4A7.5 7.5 0 1 1 20 12Z" /><path d="M9 11.5h6" /></>,
  star: <path d="m12 4 2.4 5 5.6.8-4 3.9 1 5.5-5-2.7-5 2.7 1-5.5-4-3.9 5.6-.8z" />,
  sparkle: <><path d="M12 3.5 13.7 9 19 10.7 13.7 12.4 12 18l-1.7-5.6L5 10.7 10.3 9z" /><path d="M18.5 16.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
  filter: <path d="M4 5h16l-6 7v6l-4 2v-8z" />,
  layers: <><path d="m12 3 8 4.5-8 4.5-8-4.5z" /><path d="m4 12 8 4.5 8-4.5" /><path d="m4 16.5 8 4.5 8-4.5" /></>,
  link: <><path d="M10 13.5a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10.5a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 0 0 5.7 5.7l1-1" /></>,
  dot: <circle cx="12" cy="12" r="4" />,
};

export default function Icon({ name, size = 16, strokeWidth = 1.75, fill = false, className = '', title }) {
  const path = PATHS[name];
  if (!path) return null;

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : 'true'}
      role={title ? 'img' : undefined}
      focusable="false"
    >
      {title && <title>{title}</title>}
      {path}
    </svg>
  );
}
