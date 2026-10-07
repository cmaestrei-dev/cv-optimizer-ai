// Íconos de trazo simple (sin librerías): navegación y acciones.
const base = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export const InboxIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base}><path d="M3 13l2.5-7h13L21 13v6H3z" /><path d="M3 13h5l1.5 2.5h5L16 13h5" /></svg>
);
export const BriefcaseIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base}><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V5h6v2M3 12h18" /></svg>
);
export const UserIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base}><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" /></svg>
);
export const ChartIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></svg>
);
