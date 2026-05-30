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
    return this.recipes().filter(r =>
      r.title.toLowerCase().includes(q) &&
      (course === null || r.course === course) &&
      (!hp || (r.protein_per_person != null && r.protein_per_person >= this.HIGH_PROTEIN_G)) &&
      (!lc || (r.calories_per_person != null && r.calories_per_person <= this.LOW_CALORIE_KCAL))
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
}
