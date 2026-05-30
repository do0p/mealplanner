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
  loading = signal(true);

  courses = computed(() => {
    const seen = new Set<string>();
    for (const r of this.recipes()) {
      if (r.course) seen.add(r.course);
    }
    return [...seen].sort();
  });

  filtered = computed(() => {
    const q = this.query().toLowerCase();
    const course = this.selectedCourse();
    const hp = this.highProtein();
    const lc = this.lowCalorie();
    const veg = this.vegetarian();
    const vgn = this.vegan();
    const fav = this.favourites();
    return this.recipes().filter(r =>
      r.title.toLowerCase().includes(q) &&
      (course === null || r.course === course) &&
      (!hp  || (r.protein_per_person != null && r.protein_per_person >= this.HIGH_PROTEIN_G)) &&
      (!lc  || (r.calories_per_person != null && r.calories_per_person <= this.LOW_CALORIE_KCAL)) &&
      (!veg || r.is_vegetarian) &&
      (!vgn || r.is_vegan) &&
      (!fav || r.is_favourite)
    );
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

  toggleFavourite(event: Event, r: RecipeSummary) {
    event.preventDefault();
    event.stopPropagation();
    const next = !r.is_favourite;
    this.recipes.update(list => list.map(x => x.id === r.id ? { ...x, is_favourite: next } : x));
    this.api.updateRecipe(r.id, { is_favourite: next }).subscribe();
  }
}
