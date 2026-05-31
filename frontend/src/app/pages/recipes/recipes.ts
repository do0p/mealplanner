import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../api.service';
import { RecipeFilterService } from '../../recipe-filter.service';
import { RecipeSummary } from '../../models';

@Component({
  selector: 'app-recipes',
  imports: [DecimalPipe, FormsModule, RouterLink],
  templateUrl: './recipes.html',
  styleUrl: './recipes.scss',
})
export class RecipesPage implements OnInit {
  private api = inject(ApiService);
  private filterSvc = inject(RecipeFilterService);

  readonly HIGH_PROTEIN_G = 40;
  readonly LOW_CALORIE_KCAL = 500;

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
  sortAz = this.filterSvc.sortAz;

  // Recipes matching all active filters except the course constraint —
  // used to determine which course chips are still reachable.
  private withoutCourse = computed(() => {
    const q = this.query().toLowerCase();
    const hp = this.highProtein();
    const lc = this.lowCalorie();
    const veg = this.vegetarian();
    const vgn = this.vegan();
    const fav = this.favourites();
    const wtt = this.wantToTry();
    return this.recipes().filter(r =>
      r.title.toLowerCase().includes(q) &&
      (!hp  || (r.protein_per_person != null && r.protein_per_person >= this.HIGH_PROTEIN_G)) &&
      (!lc  || (r.calories_per_person != null && r.calories_per_person <= this.LOW_CALORIE_KCAL)) &&
      (!veg || r.is_vegetarian) &&
      (!vgn || r.is_vegan) &&
      (!fav || r.is_favourite) &&
      (!wtt || r.is_want_to_try)
    );
  });

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
    this.wantToTry()
  );

  filtered = computed(() => {
    const q = this.query().toLowerCase();
    const course = this.selectedCourse();
    const hp = this.highProtein();
    const lc = this.lowCalorie();
    const veg = this.vegetarian();
    const vgn = this.vegan();
    const fav = this.favourites();
    const wtt = this.wantToTry();
    let result = this.recipes().filter(r =>
      r.title.toLowerCase().includes(q) &&
      (course === null || r.course === course) &&
      (!hp  || (r.protein_per_person != null && r.protein_per_person >= this.HIGH_PROTEIN_G)) &&
      (!lc  || (r.calories_per_person != null && r.calories_per_person <= this.LOW_CALORIE_KCAL)) &&
      (!veg || r.is_vegetarian) &&
      (!vgn || r.is_vegan) &&
      (!fav || r.is_favourite) &&
      (!wtt || r.is_want_to_try)
    );
    if (this.sortAz()) {
      result = [...result].sort((a, b) => a.title.localeCompare(b.title));
    }
    return result;
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
    this.api.updateRecipe(r.id, { is_favourite: next }).subscribe();
  }

  toggleWantToTry(event: Event, r: RecipeSummary) {
    event.preventDefault();
    event.stopPropagation();
    const next = !r.is_want_to_try;
    this.recipes.update(list => list.map(x => x.id === r.id ? { ...x, is_want_to_try: next } : x));
    this.api.updateRecipe(r.id, { is_want_to_try: next }).subscribe();
  }
}
