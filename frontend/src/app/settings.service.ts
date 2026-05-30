import { Injectable } from '@angular/core';

const DEFAULT_TZ = 'Europe/Vienna';

export function formatQty(qty: number | null, unit: string | null): string {
  if (qty == null) return '';
  const u = unit === 'pcs' ? '' : (unit ?? '');
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
