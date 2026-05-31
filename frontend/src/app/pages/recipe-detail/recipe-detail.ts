import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../api.service';
import { Recipe } from '../../models';
import { formatQty, SettingsService } from '../../settings.service';
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
  imports: [DecimalPipe, FormsModule, RouterLink],
  templateUrl: './recipe-detail.html',
  styleUrl: './recipe-detail.scss',
})
export class RecipeDetailPage implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private toast = inject(ToastService);
  private settings = inject(SettingsService);

  recipe = signal<Recipe | null>(null);
  loading = signal(true);
  people = signal(2);
  deleting = signal(false);
  editing = signal(false);
  saving = signal(false);

  draftTitle = signal('');
  draftIngredients = signal<IngredientDraft[]>([]);
  draftSteps = signal<string[]>([]);
  draftCourse = signal<string | null>(null);
  draftVegetarian = signal(false);
  draftVegan = signal(false);

  scaledIngredients = computed(() => {
    const r = this.recipe();
    const n = this.people();
    if (!r) return [];
    return r.ingredients.map(ing => {
      let qty = ing.quantity_per_person != null ? ing.quantity_per_person * n : null;
      if (qty != null && ing.whole_unit_only) qty = Math.max(1, Math.round(qty));
      return { ...ing, display: formatQty(qty, ing.unit) };
    });
  });

  sourceUrl = computed(() => {
    const r = this.recipe();
    return r ? this.api.recipeSourceUrl(r.id) : '';
  });

  scaledNutrition = computed(() => {
    const r = this.recipe();
    if (!r) return null;
    const cal = r.calories_per_person;
    const prot = r.protein_per_person;
    if (cal == null && prot == null) return null;
    return { cal, prot };
  });

  ngOnInit() {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    this.api.getRecipe(id).subscribe({
      next: r => {
        this.recipe.set(r);
        this.people.set(this.settings.defaultServings());
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
    this.draftCourse.set(r.course ?? null);
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
      course: this.draftCourse() || null,
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

  toggleFavourite() {
    const r = this.recipe()!;
    const next = !r.is_favourite;
    this.recipe.update(cur => cur ? { ...cur, is_favourite: next } : cur);
    this.api.updateRecipe(r.id, { is_favourite: next }).subscribe();
  }

  toggleWantToTry() {
    const r = this.recipe()!;
    const next = !r.is_want_to_try;
    this.recipe.update(cur => cur ? { ...cur, is_want_to_try: next } : cur);
    this.api.updateRecipe(r.id, { is_want_to_try: next }).subscribe();
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
