import { Injectable, signal } from '@angular/core';

const TZ_KEY = 'mp:timezone';
const DEFAULT_TZ = 'Europe/Berlin';

export const TIMEZONES = [
  { value: 'UTC',                  label: 'UTC' },
  { value: 'Europe/London',        label: 'London (GMT/BST)' },
  { value: 'Europe/Berlin',        label: 'Berlin (CET/CEST)' },
  { value: 'Europe/Helsinki',      label: 'Helsinki (EET/EEST)' },
  { value: 'America/New_York',     label: 'New York (ET)' },
  { value: 'America/Los_Angeles',  label: 'Los Angeles (PT)' },
];

@Injectable({ providedIn: 'root' })
export class SettingsService {
  readonly timezone = signal<string>(localStorage.getItem(TZ_KEY) ?? DEFAULT_TZ);

  setTimezone(tz: string): void {
    localStorage.setItem(TZ_KEY, tz);
    this.timezone.set(tz);
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
      timeZone: this.timezone(),
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }
}
