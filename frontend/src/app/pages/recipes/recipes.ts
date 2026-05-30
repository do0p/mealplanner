import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../api.service';
import { RecipeSummary } from '../../models';

@Component({
  selector: 'app-recipes',
  imports: [DecimalPipe, FormsModule, RouterLink],
  templateUrl: './recipes.html',
  styleUrl: './recipes.scss',
})
export class RecipesPage implements OnInit {
  private api = inject(ApiService);

  readonly HIGH_PROTEIN_G = 40;
  readonly LOW_CALORIE_KCAL = 600;

  recipes = signal<RecipeSummary[]>([]);
  query = signal('');
  selectedCourse = signal<string | null>(null);
  highProtein = signal(false);
  lowCalorie = signal(false);
  vegetarian = signal(false);
  vegan = signal(false);
  favourites = signal(false);
  wantToTry = signal(false);
  sortAz = signal(false);
  loading = signal(true);

  courses = computed(() => {
    const seen = new Set<string>();
    for (const r of this.recipes()) {
      if (r.course) seen.add(r.course);
    }
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
    this.query.set('');
    this.selectedCourse.set(null);
    this.highProtein.set(false);
    this.lowCalorie.set(false);
    this.vegetarian.set(false);
    this.vegan.set(false);
    this.favourites.set(false);
    this.wantToTry.set(false);
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
