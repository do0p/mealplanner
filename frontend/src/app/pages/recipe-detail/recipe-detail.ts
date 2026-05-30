import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../api.service';
import { Recipe } from '../../models';

function formatQty(qty: number | null, unit: string | null): string {
  if (qty == null) return '';
  const u = unit === 'pcs' ? '' : (unit ?? '');
  const r = unit === 'pcs' ? Math.ceil(qty - 1e-9) : qty >= 10 ? Math.round(qty) : Math.round(qty * 10) / 10;
  return u ? `${r} ${u}` : `${r}`;
}

@Component({
  selector: 'app-recipe-detail',
  imports: [FormsModule, RouterLink],
  templateUrl: './recipe-detail.html',
  styleUrl: './recipe-detail.scss',
})
export class RecipeDetailPage implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  recipe = signal<Recipe | null>(null);
  loading = signal(true);
  people = signal(2);
  deleting = signal(false);

  scaledIngredients = computed(() => {
    const r = this.recipe();
    const n = this.people();
    if (!r) return [];
    return r.ingredients.map(ing => ({
      ...ing,
      display: formatQty(
        ing.quantity_per_person != null ? ing.quantity_per_person * n : null,
        ing.unit,
      ),
    }));
  });

  sourceUrl = computed(() => {
    const r = this.recipe();
    return r ? this.api.recipeSourceUrl(r.id) : '';
  });

  ngOnInit() {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    this.api.getRecipe(id).subscribe({
      next: r => {
        this.recipe.set(r);
        this.people.set(r.base_servings ?? 2);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  delete() {
    const r = this.recipe();
    if (!r || !confirm(`Delete "${r.title}"?`)) return;
    this.deleting.set(true);
    this.api.deleteRecipe(r.id).subscribe(() => this.router.navigate(['/recipes']));
  }
}
