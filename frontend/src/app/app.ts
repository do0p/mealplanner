import { Component, inject, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { APP_VERSION } from './version';
import { ApiService } from './api.service';
import { SettingsService } from './settings.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  version = APP_VERSION;
  private api = inject(ApiService);
  private settings = inject(SettingsService);

  ngOnInit(): void {
    this.api.getVersion().subscribe(v => {
      this.settings.setTimezone(v.display_timezone);
    });
  }
}
