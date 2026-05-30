import { Component, inject, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { APP_VERSION } from './version';
import { ApiService } from './api.service';
import { SettingsService } from './settings.service';
import { ToastService } from './toast.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  version = APP_VERSION;
  private api = inject(ApiService);
  settings = inject(SettingsService);
  toast = inject(ToastService);

  ngOnInit(): void {
    this.api.getVersion().subscribe(v => {
      this.settings.setTimezone(v.display_timezone);
    });
  }
}
