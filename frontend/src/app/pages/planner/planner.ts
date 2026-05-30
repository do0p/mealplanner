import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../api.service';
import { Plan, PlanEntry, PlanSummary, RecipeSummary } from '../../models';

export const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
export const MEALS = ['Breakfast', 'Lunch', 'Dinner'];

export function slotKey(day: string, meal: string): string {
  return `${day}-${meal}`;
}

@Component({
  selector: 'app-planner',
  imports: [FormsModule],
  templateUrl: './planner.html',
  styleUrl: './planner.scss',
})
export class PlannerPage implements OnInit {
  private api = inject(ApiService);
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

  pickerResults = computed(() => {
    const q = this.pickerQuery().toLowerCase();
    return this.allRecipes().filter(r => r.title.toLowerCase().includes(q));
  });

  // current plan entries indexed by slot key for O(1) lookup
  entryMap = computed<Record<string, PlanEntry>>(() => {
    const plan = this.selectedPlan();
    if (!plan) return {};
    return Object.fromEntries(plan.entries.map(e => [e.slot, e]));
  });

  ngOnInit() {
    this.api.getPlans().subscribe(p => this.plans.set(p));
    this.api.getRecipes('accepted').subscribe(r => this.allRecipes.set(r));
  }

  selectPlan(id: number) {
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
    });
  }

  deletePlan() {
    const plan = this.selectedPlan();
    if (!plan || !confirm(`Delete plan "${plan.name}"?`)) return;
    this.api.deletePlan(plan.id).subscribe(() => {
      this.plans.update(pl => pl.filter(p => p.id !== plan.id));
      this.selectedPlan.set(null);
    });
  }

  openPicker(day: string, meal: string) {
    this.pickerSlot.set(slotKey(day, meal));
    const existing = this.entryMap()[slotKey(day, meal)];
    this.pickerPeople.set(existing?.people ?? 2);
    this.pickerQuery.set('');
  }

  closePicker() { this.pickerSlot.set(null); }

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
