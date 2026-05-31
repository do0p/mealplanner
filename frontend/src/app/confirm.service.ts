import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ConfirmService {
  private _resolve: ((v: boolean) => void) | null = null;
  dialog = signal<{ message: string } | null>(null);

  confirm(message: string): Promise<boolean> {
    return new Promise(resolve => {
      this._resolve = resolve;
      this.dialog.set({ message });
    });
  }

  accept(): void {
    this._resolve?.(true);
    this._resolve = null;
    this.dialog.set(null);
  }

  cancel(): void {
    this._resolve?.(false);
    this._resolve = null;
    this.dialog.set(null);
  }
}
