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

  ngOnInit() {
    const id = Number(this.route.snapshot.paramMap.get('planId'));
    this.planId.set(id);
    this.api.getShoppingList(id).subscribe({
      next: s => { this.sl.set(s); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  toggle(key: string) {
    this.checked.update(s => {
      const next = new Set(s);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  isChecked(key: string): boolean {
    return this.checked().has(key);
  }

  itemKey(cat: string, name: string): string {
    return `${cat}::${name}`;
  }

  uncheckAll() { this.checked.set(new Set()); }

  print() { window.print(); }
}
