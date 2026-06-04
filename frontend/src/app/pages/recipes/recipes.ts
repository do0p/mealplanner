import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../api.service';
import { RecipeSummary } from '../../models';
import { RecipeFilterService } from '../../recipe-filter.service';
import { ToastService } from '../../toast.service';

@Component({
  selector: 'app-recipes',
  imports: [DecimalPipe, FormsModule, RouterLink],
  templateUrl: './recipes.html',
  styleUrl: './recipes.scss',
})
export class RecipesPage implements OnInit {
  private api = inject(ApiService);
  private filterSvc = inject(RecipeFilterService);
  private toast = inject(ToastService);

  readonly HIGH_PROTEIN_G = 40;
  readonly LOW_CALORIE_KCAL = 500;

  private _ketoFatPct(r: RecipeSummary): number | null {
    const f = r.fat_per_person, c = r.carbs_per_person, p = r.protein_per_person;
    if (f == null || c == null) return null;
    const total = f * 9 + (p ?? 0) * 4 + c * 4;
    return total > 0 ? (f * 9 / total) * 100 : null;
  }

  private _ketoCarbsPct(r: RecipeSummary): number | null {
    const f = r.fat_per_person, c = r.carbs_per_person, p = r.protein_per_person;
    if (f == null || c == null) return null;
    const total = f * 9 + (p ?? 0) * 4 + c * 4;
    return total > 0 ? (c * 4 / total) * 100 : null;
  }

  private _isKeto(r: RecipeSummary): boolean {
    const fat = this._ketoFatPct(r), carbs = this._ketoCarbsPct(r);
    return fat != null && carbs != null && fat > 70 && carbs < 5;
  }

  recipes = signal<RecipeSummary[]>([]);
  loading = signal(true);

  // Expose filter service signals directly so the template is unchanged.
  query = this.filterSvc.query;
  selectedCourse = this.filterSvc.selectedCourse;
  highProtein = this.filterSvc.highProtein;
  lowCalorie = this.filterSvc.lowCalorie;
  vegetarian = this.filterSvc.vegetarian;
  vegan = this.filterSvc.vegan;
  favourites = this.filterSvc.favourites;
  wantToTry = this.filterSvc.wantToTry;
  keto = this.filterSvc.keto;
  private _matches(r: RecipeSummary): boolean {
    return (
      r.title.toLowerCase().includes(this.query().toLowerCase()) &&
      (!this.highProtein() || (r.protein_per_person != null && r.protein_per_person >= this.HIGH_PROTEIN_G)) &&
      (!this.lowCalorie()  || (r.calories_per_person != null && r.calories_per_person <= this.LOW_CALORIE_KCAL)) &&
      (!this.vegetarian()  || r.is_vegetarian) &&
      (!this.vegan()       || r.is_vegan) &&
      (!this.favourites()  || r.is_favourite) &&
      (!this.wantToTry()   || r.is_want_to_try) &&
      (!this.keto()        || this._isKeto(r))
    );
  }

  // Recipes matching all active filters except the course constraint —
  // used to determine which course chips are still reachable.
  private withoutCourse = computed(() => this.recipes().filter(r => this._matches(r)));

  // Course chips: only courses reachable from the current filter state,
  // plus the selected course so it can always be deactivated.
  courses = computed(() => {
    const sel = this.selectedCourse();
    const seen = new Set<string>();
    for (const r of this.withoutCourse()) {
      if (r.course) seen.add(r.course);
    }
    if (sel) seen.add(sel);
    return [...seen].sort();
  });

  hasFilters = computed(() =>
    this.query() !== '' ||
    this.selectedCourse() !== null ||
    this.highProtein() ||
    this.lowCalorie() ||
    this.vegetarian() ||
    this.vegan() ||
    this.favourites() ||
    this.wantToTry() ||
    this.keto()
  );

  filtered = computed(() => {
    const course = this.selectedCourse();
    return this.withoutCourse().filter(r => course === null || r.course === course);
  });

  // Boolean chip visibility: active filters always stay visible;
  // inactive ones only appear when they would match ≥1 recipe in the current result.
  canFilterFavourites = computed(() =>
    this.favourites() || this.filtered().some(r => r.is_favourite)
  );
  canFilterWantToTry = computed(() =>
    this.wantToTry() || this.filtered().some(r => r.is_want_to_try)
  );
  canFilterVegetarian = computed(() =>
    this.vegetarian() || this.filtered().some(r => r.is_vegetarian)
  );
  canFilterVegan = computed(() =>
    this.vegan() || this.filtered().some(r => r.is_vegan)
  );
  canFilterHighProtein = computed(() =>
    this.highProtein() || this.filtered().some(r =>
      r.protein_per_person != null && r.protein_per_person >= this.HIGH_PROTEIN_G)
  );
  canFilterLowCalorie = computed(() =>
    this.lowCalorie() || this.filtered().some(r =>
      r.calories_per_person != null && r.calories_per_person <= this.LOW_CALORIE_KCAL)
  );
  canFilterKeto = computed(() =>
    this.keto() || this.filtered().some(r => this._isKeto(r))
  );

  ngOnInit() {
    this.api.getRecipes('accepted').subscribe({
      next: r => { this.recipes.set(r); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  toggleCourse(course: string) {
    this.selectedCourse.update(c => c === course ? null : course);
  }

  clearFilters() {
    this.filterSvc.clear();
  }

  toggleFavourite(event: Event, r: RecipeSummary) {
    event.preventDefault();
    event.stopPropagation();
    const next = !r.is_favourite;
    this.recipes.update(list => list.map(x => x.id === r.id ? { ...x, is_favourite: next } : x));
    this.api.updateRecipe(r.id, { is_favourite: next }).subscribe({
      error: () => {
        this.recipes.update(list => list.map(x => x.id === r.id ? { ...x, is_favourite: r.is_favourite } : x));
        this.toast.show('Update failed', 'error');
      },
    });
  }

  toggleWantToTry(event: Event, r: RecipeSummary) {
    event.preventDefault();
    event.stopPropagation();
    const next = !r.is_want_to_try;
    this.recipes.update(list => list.map(x => x.id === r.id ? { ...x, is_want_to_try: next } : x));
    this.api.updateRecipe(r.id, { is_want_to_try: next }).subscribe({
      error: () => {
        this.recipes.update(list => list.map(x => x.id === r.id ? { ...x, is_want_to_try: r.is_want_to_try } : x));
        this.toast.show('Update failed', 'error');
      },
    });
  }
}
