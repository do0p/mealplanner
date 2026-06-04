import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../api.service';
import { ConfirmService } from '../../confirm.service';
import { Plan, PlanEntry, PlanSummary, Recipe, RecipeSummary } from '../../models';
import { formatQty } from '../../settings.service';

export const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
export const MEALS = ['Breakfast', 'Lunch', 'Dinner'];

export function slotKey(day: string, meal: string): string {
  return `${day}-${meal}`;
}

@Component({
  selector: 'app-planner',
  imports: [FormsModule, RouterLink],
  templateUrl: './planner.html',
  styleUrl: './planner.scss',
})
export class PlannerPage implements OnInit {
  private api = inject(ApiService);
  private confirm = inject(ConfirmService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  days = DAYS;
  meals = MEALS;

  plans = signal<PlanSummary[]>([]);
  selectedPlan = signal<Plan | null>(null);
  allRecipes = signal<RecipeSummary[]>([]);
  saving = signal(false);
  newPlanName = signal('');
  creatingPlan = signal(false);

  pickerSlot = signal<string | null>(null);
  pickerPeople = signal(2);
  pickerQuery = signal('');
  pickerCourse = signal<string | null>(null);
  pickerFavourites = signal(false);
  pickerVegetarian = signal(false);
  pickerVegan = signal(false);
  pickerWantToTry = signal(false);

  hoveredPickerRecipe = signal<RecipeSummary | null>(null);
  hoveredPickerDetail = signal<Recipe | null>(null);
  private recipeCache = new Map<number, Recipe>();
  readonly formatQty = formatQty;

  pickerCourses = computed(() => {
    const seen = new Set<string>();
    for (const r of this.allRecipes()) {
      if (r.course) seen.add(r.course);
    }
    return [...seen].sort();
  });

  pickerResults = computed(() => {
    const q = this.pickerQuery().toLowerCase();
    const course = this.pickerCourse();
    const fav = this.pickerFavourites();
    const veg = this.pickerVegetarian();
    const vgn = this.pickerVegan();
    const wtt = this.pickerWantToTry();
    return this.allRecipes().filter(r =>
      r.title.toLowerCase().includes(q) &&
      (course === null || r.course === course) &&
      (!fav || r.is_favourite) &&
      (!veg || r.is_vegetarian) &&
      (!vgn || r.is_vegan) &&
      (!wtt || r.is_want_to_try)
    );
  });

  pickerHoverNutrition = computed(() => {
    const r = this.hoveredPickerRecipe();
    if (!r) return null;
    const n = this.pickerPeople();
    const cal   = r.calories_per_person != null ? Math.round(r.calories_per_person * n) : null;
    const prot  = r.protein_per_person  != null ? Math.round(r.protein_per_person  * n) : null;
    const fat   = r.fat_per_person      != null ? Math.round(r.fat_per_person      * n) : null;
    const carbs = r.carbs_per_person    != null ? Math.round(r.carbs_per_person    * n) : null;
    if (cal == null && prot == null && fat == null && carbs == null) return null;
    return { cal, prot, fat, carbs };
  });

  pickerHoverIngredients = computed(() => {
    const d = this.hoveredPickerDetail();
    if (!d) return null;
    const n = this.pickerPeople();
    return d.ingredients.map(ing => {
      let qty = ing.quantity_per_person != null ? ing.quantity_per_person * n : null;
      if (qty != null && ing.whole_unit_only) qty = Math.max(1, Math.round(qty));
      return { name: ing.name, display: formatQty(qty, ing.unit) };
    });
  });

  // current plan entries indexed by slot key for O(1) lookup
  entryMap = computed<Record<string, PlanEntry>>(() => {
    const plan = this.selectedPlan();
    if (!plan) return {};
    return Object.fromEntries(plan.entries.map(e => [e.slot, e]));
  });

  ngOnInit() {
    const initialPlanId = Number(this.route.snapshot.queryParamMap.get('plan')) || null;
    this.api.getPlans().subscribe(p => {
      this.plans.set(p);
      if (initialPlanId && p.some(pl => pl.id === initialPlanId)) {
        this.api.getPlan(initialPlanId).subscribe(plan => this.selectedPlan.set(plan));
      }
    });
    this.api.getRecipes('accepted').subscribe(r => this.allRecipes.set(r));
  }

  selectPlan(id: number) {
    this.router.navigate([], { queryParams: { plan: id }, replaceUrl: true });
    this.api.getPlan(id).subscribe(p => this.selectedPlan.set(p));
  }

  createPlan() {
    const name = this.newPlanName().trim();
    if (!name) return;
    this.creatingPlan.set(true);
    this.api.createPlan(name).subscribe(p => {
      this.plans.update(pl => [{ id: p.id, name: p.name, created_at: p.created_at, entry_count: 0 }, ...pl]);
      this.selectedPlan.set(p);
      this.newPlanName.set('');
      this.creatingPlan.set(false);
      this.router.navigate([], { queryParams: { plan: p.id }, replaceUrl: true });
    });
  }

  async deletePlan() {
    const plan = this.selectedPlan();
    if (!plan) return;
    if (!await this.confirm.confirm(`Delete plan "${plan.name}"?`)) return;
    this.api.deletePlan(plan.id).subscribe(() => {
      this.plans.update(pl => pl.filter(p => p.id !== plan.id));
      this.selectedPlan.set(null);
      this.router.navigate([], { queryParams: {}, replaceUrl: true });
    });
  }

  openPicker(day: string, meal: string) {
    this.pickerSlot.set(slotKey(day, meal));
    const existing = this.entryMap()[slotKey(day, meal)];
    this.pickerPeople.set(existing?.people ?? 2);
    this.pickerQuery.set('');
    this.pickerCourse.set(null);
    this.pickerFavourites.set(false);
    this.pickerVegetarian.set(false);
    this.pickerVegan.set(false);
    this.pickerWantToTry.set(false);
  }

  closePicker() {
    this.pickerSlot.set(null);
    this.hoveredPickerRecipe.set(null);
    this.hoveredPickerDetail.set(null);
  }

  hoverPickerItem(r: RecipeSummary) {
    this.hoveredPickerRecipe.set(r);
    if (this.recipeCache.has(r.id)) {
      this.hoveredPickerDetail.set(this.recipeCache.get(r.id)!);
      return;
    }
    this.hoveredPickerDetail.set(null);
    this.api.getRecipe(r.id).subscribe(detail => {
      this.recipeCache.set(r.id, detail);
      if (this.hoveredPickerRecipe()?.id === r.id) {
        this.hoveredPickerDetail.set(detail);
      }
    });
  }

  unhoverPickerItem() {
    this.hoveredPickerRecipe.set(null);
    this.hoveredPickerDetail.set(null);
  }

  pickRecipe(recipe: RecipeSummary) {
    const slot = this.pickerSlot();
    const plan = this.selectedPlan();
    if (!slot || !plan) return;

    const entries = plan.entries.filter(e => e.slot !== slot);
    const newEntry: PlanEntry = {
      id: 0,
      recipe_id: recipe.id,
      recipe_title: recipe.title,
      slot,
      people: this.pickerPeople(),
      sort_order: entries.length,
    };
    const updated = [...entries, newEntry];
    this.saveEntries(plan.id, updated);
    this.closePicker();
  }

  clearSlot(day: string, meal: string) {
    const plan = this.selectedPlan();
    if (!plan) return;
    const slot = slotKey(day, meal);
    const entries = plan.entries.filter(e => e.slot !== slot);
    this.saveEntries(plan.id, entries);
  }

  updatePeople(day: string, meal: string, people: number) {
    const plan = this.selectedPlan();
    if (!plan) return;
    const slot = slotKey(day, meal);
    const entries = plan.entries.map(e =>
      e.slot === slot ? { ...e, people: Math.max(1, people) } : e
    );
    this.saveEntries(plan.id, entries);
  }

  private saveEntries(planId: number, entries: PlanEntry[]) {
    this.saving.set(true);
    this.api.updatePlan(planId, {
      entries: entries.map((e, i) => ({
        recipe_id: e.recipe_id,
        slot: e.slot,
        people: e.people,
        sort_order: i,
      })),
    }).subscribe(p => {
      this.selectedPlan.set(p);
      this.saving.set(false);
    });
  }

  viewShoppingList() {
    const plan = this.selectedPlan();
    if (plan) this.router.navigate(['/shopping-list', plan.id]);
  }
}
