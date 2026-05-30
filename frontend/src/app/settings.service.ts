import { Injectable } from '@angular/core';

const DEFAULT_TZ = 'Europe/Vienna';

const FRACS: [number, string][] = [
  [0.25,     '1/4'],
  [1 / 3,    '1/3'],
  [0.5,      '1/2'],
  [2 / 3,    '2/3'],
  [0.75,     '3/4'],
];
const FRAC_TOL = 0.07;

function fracStr(frac: number): string | null {
  let best: string | null = null;
  let bestDist = FRAC_TOL;
  for (const [val, label] of FRACS) {
    const dist = Math.abs(frac - val);
    if (dist < bestDist) { bestDist = dist; best = label; }
  }
  return best;
}

export function formatQty(qty: number | null, unit: string | null): string {
  const u = unit === 'pcs' ? '' : (unit ?? '');
  if (qty == null) return u;

  // Non-metric culinary units: prefer fraction notation.
  if (unit !== 'g' && unit !== 'ml' && unit !== 'pcs') {
    const whole = Math.floor(qty);
    const frac = qty - whole;
    const label = fracStr(frac);
    if (label) {
      const q = whole > 0 ? `${whole} ${label}` : label;
      return u ? `${q} ${u}` : q;
    }
  }

  // Standard rounding for metric units or non-fractional values.
  let r: number;
  if (unit === 'pcs') {
    r = Math.ceil(qty - 1e-9);
  } else if ((unit === 'g' || unit === 'ml') && qty >= 10) {
    r = Math.round(qty / 5) * 5;
  } else if (qty >= 10) {
    r = Math.round(qty);
  } else {
    r = Math.round(qty * 10) / 10;
  }
  return u ? `${r} ${u}` : `${r}`;
}

function makeFmt(tz: string): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat('de-DE', {
    timeZone: tz,
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private _fmt = makeFmt(DEFAULT_TZ);

  setTimezone(tz: string): void {
    this._fmt = makeFmt(tz);
  }

  formatDate(iso: string): string {
    // SQLite strips timezone info; treat naive strings as UTC
    const s = /Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z';
    return this._fmt.format(new Date(s));
  }
}
