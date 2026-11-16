// Íconos de trazo simple (sin librerías), todos con el mismo trazo: navegación, estados y acciones.
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
export const CheckIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2.4}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
);
export const CrossIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2.4}><path d="M6.5 6.5l11 11M17.5 6.5l-11 11" /></svg>
);
export const HalfIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2}><circle cx="12" cy="12" r="7.5" /><path d="M12 4.5a7.5 7.5 0 010 15z" fill="currentColor" /></svg>
);
export const AlertIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2.2}><path d="M12 7v6M12 17v.01" /><circle cx="12" cy="12" r="9" /></svg>
);
export const RepeatIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2}><path d="M4 12a8 8 0 0113.7-5.6L20 9M20 4v5h-5M20 12a8 8 0 01-13.7 5.6L4 15M4 20v-5h5" /></svg>
);
export const ExternalIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5" /></svg>
);
export const CloseIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2}><path d="M7 7l10 10M17 7L7 17" /></svg>
);
export const PlusIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2}><path d="M12 5v14M5 12h14" /></svg>
);
export const ArrowIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const ChevronIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2}><path d="M9 6l6 6-6 6" /></svg>
);
export const UploadIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base} strokeWidth={2}><path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" /></svg>
);
