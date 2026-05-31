import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { EMPTY } from 'rxjs';
import { RecipeDetailPage } from './recipe-detail';
import { ApiService } from '../../api.service';
import { Ingredient, Recipe } from '../../models';

function makeIngredient(overrides: Partial<Ingredient> = {}): Ingredient {
  return {
    id: 1,
    name: 'flour',
    quantity_per_person: 100,
    unit: 'g',
    category: null,
    raw_text: null,
    whole_unit_only: false,
    ...overrides,
  };
}

function makeRecipe(ingredients: Ingredient[] = []): Recipe {
  return {
    id: 1,
    title: 'Test',
    base_servings: 2,
    course: null,
    calories_per_person: null,
    protein_per_person: null,
    is_vegetarian: false,
    is_vegan: false,
    is_favourite: false,
    is_want_to_try: false,
    status: 'accepted',
    created_at: '2024-01-01T00:00:00Z',
    notes: null,
    source_format: null,
    source_file: null,
    import_job_id: null,
    ingredients,
    steps: [],
  };
}

describe('RecipeDetailPage — scaledIngredients', () => {
  let component: RecipeDetailPage;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [RecipeDetailPage],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => '1' } } } },
        { provide: ApiService, useValue: { getRecipe: () => EMPTY, recipeSourceUrl: () => '' } },
      ],
    });
    component = TestBed.createComponent(RecipeDetailPage).componentInstance;
  });

  it('returns empty list when recipe is null', () => {
    expect(component.scaledIngredients()).toEqual([]);
  });

  it('scales quantity by number of people', () => {
    component.recipe.set(makeRecipe([makeIngredient({ quantity_per_person: 50, unit: 'g' })]));
    component.people.set(4);
    expect(component.scaledIngredients()[0].display).toBe('200 g');
  });

  it('handles null quantity gracefully', () => {
    component.recipe.set(makeRecipe([makeIngredient({ quantity_per_person: null, unit: 'g' })]));
    component.people.set(2);
    expect(component.scaledIngredients()[0].display).toBe('g');
  });

  it('rounds whole_unit_only to nearest integer instead of showing fractions', () => {
    // 0.5 * 3 = 1.5 → round → 2
    component.recipe.set(makeRecipe([makeIngredient({ quantity_per_person: 0.5, unit: null, whole_unit_only: true })]));
    component.people.set(3);
    expect(component.scaledIngredients()[0].display).toBe('2');
  });

  it('rounds down for whole_unit_only when fraction is below 0.5', () => {
    // 1/3 * 4 = 1.333 → round → 1 (not 2)
    component.recipe.set(makeRecipe([makeIngredient({ quantity_per_person: 1 / 3, unit: null, whole_unit_only: true })]));
    component.people.set(4);
    expect(component.scaledIngredients()[0].display).toBe('1');
  });

  it('never drops whole_unit_only ingredient below 1', () => {
    // 1/3 * 1 = 0.333 → round → 0 → clamped to 1
    component.recipe.set(makeRecipe([makeIngredient({ quantity_per_person: 1 / 3, unit: null, whole_unit_only: true })]));
    component.people.set(1);
    expect(component.scaledIngredients()[0].display).toBe('1');
  });

  it('shows fraction for non-whole-unit ingredients with the same quantity', () => {
    component.recipe.set(makeRecipe([makeIngredient({ quantity_per_person: 0.5, unit: null, whole_unit_only: false })]));
    component.people.set(3);
    expect(component.scaledIngredients()[0].display).toBe('1 1/2');
  });

  it('passes whole_unit_only flag through to the result', () => {
    component.recipe.set(makeRecipe([makeIngredient({ whole_unit_only: true })]));
    component.people.set(1);
    expect(component.scaledIngredients()[0].whole_unit_only).toBe(true);
  });
});
