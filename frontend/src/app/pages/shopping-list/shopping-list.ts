import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../api.service';
import { ShoppingList } from '../../models';

@Component({
  selector: 'app-shopping-list',
  imports: [RouterLink],
  templateUrl: './shopping-list.html',
  styleUrl: './shopping-list.scss',
})
export class ShoppingListPage implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);

  sl = signal<ShoppingList | null>(null);
  planId = signal(0);
  loading = signal(true);
  checked = signal<Set<string>>(new Set());

  totalItems = computed(() =>
    this.sl()?.categories.reduce((sum, cat) => sum + cat.items.length, 0) ?? 0
  );

  private _storageKey(id: number) { return `mp:sl:checked:${id}`; }

  ngOnInit() {
    const id = Number(this.route.snapshot.paramMap.get('planId'));
    this.planId.set(id);
    const stored = localStorage.getItem(this._storageKey(id));
    if (stored) {
      try { this.checked.set(new Set(JSON.parse(stored))); } catch { /* ignore bad data */ }
    }
    this.api.getShoppingList(id).subscribe({
      next: s => { this.sl.set(s); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  toggle(key: string) {
    this.checked.update(s => {
      const next = new Set(s);
      next.has(key) ? next.delete(key) : next.add(key);
      localStorage.setItem(this._storageKey(this.planId()), JSON.stringify([...next]));
      return next;
    });
  }

  isChecked(key: string): boolean {
    return this.checked().has(key);
  }

  itemKey(cat: string, name: string, unit: string | null): string {
    return `${cat}::${name}::${unit ?? ''}`;
  }

  uncheckAll() {
    this.checked.set(new Set());
    localStorage.removeItem(this._storageKey(this.planId()));
  }

  print() { window.print(); }
}
