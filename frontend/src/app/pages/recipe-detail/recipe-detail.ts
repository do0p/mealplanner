import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../api.service';
import { Recipe } from '../../models';
import { formatQty } from '../../settings.service';
import { ToastService } from '../../toast.service';

interface IngredientDraft {
  name: string;
  quantity_per_person: number | null;
  unit: string | null;
  category: string | null;
  raw_text: string | null;
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
  private toast = inject(ToastService);

  recipe = signal<Recipe | null>(null);
  loading = signal(true);
  people = signal(2);
  deleting = signal(false);
  editing = signal(false);
  saving = signal(false);

  draftTitle = signal('');
  draftIngredients = signal<IngredientDraft[]>([]);
  draftSteps = signal<string[]>([]);
  draftVegetarian = signal(false);
  draftVegan = signal(false);

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

  startEdit() {
    const r = this.recipe()!;
    this.draftTitle.set(r.title);
    this.draftIngredients.set(r.ingredients.map(i => ({
      name: i.name,
      quantity_per_person: i.quantity_per_person,
      unit: i.unit,
      category: i.category,
      raw_text: i.raw_text,
    })));
    this.draftSteps.set(r.steps.map(s => s.text));
    this.draftVegetarian.set(r.is_vegetarian);
    this.draftVegan.set(r.is_vegan);
    this.editing.set(true);
  }

  cancelEdit() {
    this.editing.set(false);
  }

  saveEdit() {
    const r = this.recipe()!;
    this.saving.set(true);
    this.api.updateRecipe(r.id, {
      title: this.draftTitle(),
      ingredients: this.draftIngredients(),
      steps: this.draftSteps().filter(s => s.trim()),
      is_vegetarian: this.draftVegetarian(),
      is_vegan: this.draftVegan(),
    }).subscribe({
      next: updated => {
        this.recipe.set(updated);
        this.editing.set(false);
        this.saving.set(false);
        this.toast.show('Recipe saved');
      },
      error: () => { this.saving.set(false); this.toast.show('Save failed', 'error'); },
    });
  }

  addIngredient() {
    this.draftIngredients.update(list => [...list, { name: '', quantity_per_person: null, unit: null, category: null, raw_text: null }]);
  }

  removeIngredient(i: number) {
    this.draftIngredients.update(list => list.filter((_, idx) => idx !== i));
  }

  updateIngredient(i: number, field: keyof IngredientDraft, value: string) {
    this.draftIngredients.update(list => {
      const copy = list.map(x => ({ ...x }));
      if (field === 'quantity_per_person') {
        copy[i][field] = value === '' ? null : Number(value);
      } else {
        (copy[i] as Record<string, unknown>)[field] = value === '' ? null : value;
      }
      return copy;
    });
  }

  addStep() {
    this.draftSteps.update(list => [...list, '']);
  }

  removeStep(i: number) {
    this.draftSteps.update(list => list.filter((_, idx) => idx !== i));
  }

  updateStep(i: number, value: string) {
    this.draftSteps.update(list => list.map((s, idx) => idx === i ? value : s));
  }

  delete() {
    const r = this.recipe();
    if (!r || !confirm(`Delete "${r.title}"?`)) return;
    this.deleting.set(true);
    this.api.deleteRecipe(r.id).subscribe({
      next: () => this.router.navigate(['/recipes']),
      error: () => { this.deleting.set(false); this.toast.show('Delete failed', 'error'); },
    });
  }
}
