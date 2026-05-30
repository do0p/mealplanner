import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { APP_VERSION } from './version';
import { SettingsService, TIMEZONES } from './settings.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  version = APP_VERSION;
  settings = inject(SettingsService);
  readonly timezones = TIMEZONES;

  onTzChange(e: Event): void {
    this.settings.setTimezone((e.target as HTMLSelectElement).value);
  }
}
