import { Injectable } from '@angular/core';

const TZ = 'Europe/Berlin';

export function formatQty(qty: number | null, unit: string | null): string {
  if (qty == null) return '';
  const u = unit === 'pcs' ? '' : (unit ?? '');
  const r = unit === 'pcs' ? Math.ceil(qty - 1e-9) : qty >= 10 ? Math.round(qty) : Math.round(qty * 10) / 10;
  return u ? `${r} ${u}` : `${r}`;
}

const _fmt = new Intl.DateTimeFormat('de-DE', {
  timeZone: TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

@Injectable({ providedIn: 'root' })
export class SettingsService {
  formatDate(iso: string): string {
    return _fmt.format(new Date(iso));
  }
}
