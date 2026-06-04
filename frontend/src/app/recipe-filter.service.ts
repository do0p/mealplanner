import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class RecipeFilterService {
  query = signal('');
  selectedCourse = signal<string | null>(null);
  highProtein = signal(false);
  lowCalorie = signal(false);
  vegetarian = signal(false);
  vegan = signal(false);
  favourites = signal(false);
  wantToTry = signal(false);
  keto = signal(false);
  clear() {
    this.query.set('');
    this.selectedCourse.set(null);
    this.highProtein.set(false);
    this.lowCalorie.set(false);
    this.vegetarian.set(false);
    this.vegan.set(false);
    this.favourites.set(false);
    this.wantToTry.set(false);
    this.keto.set(false);
  }
}
