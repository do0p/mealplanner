export interface Ingredient {
  id: number;
  name: string;
  quantity_per_person: number | null;
  unit: string | null;
  category: string | null;
  raw_text: string | null;
}

export interface Step {
  step_number: number;
  text: string;
}

export interface RecipeSummary {
  id: number;
  title: string;
  base_servings: number | null;
  course: string | null;
  calories_per_person: number | null;
  protein_per_person: number | null;
  is_vegetarian: boolean;
  is_vegan: boolean;
  is_favourite: boolean;
  verification_status: string;
  status: string;
  created_at: string;
}

export interface Recipe extends RecipeSummary {
  notes: string | null;
  source_format: string | null;
  source_file: string | null;
  source_pages: string | null;
  verification_notes: string | null;
  import_job_id: number | null;
  ingredients: Ingredient[];
  steps: Step[];
}

export interface PlanEntry {
  id: number;
  recipe_id: number;
  recipe_title: string;
  slot: string;
  people: number;
  sort_order: number;
}

export interface PlanSummary {
  id: number;
  name: string;
  created_at: string;
  entry_count: number;
}

export interface Plan extends PlanSummary {
  entries: PlanEntry[];
}

export interface ShoppingItem {
  name: string;
  quantity: number | null;
  unit: string | null;
  display: string;
  category: string;
  from_recipes: string[];
}

export interface ShoppingCategory {
  category: string;
  items: ShoppingItem[];
}

export interface ShoppingList {
  categories: ShoppingCategory[];
}

export interface ImportJob {
  id: number;
  filename: string;
  source_format: string;
  status: string;
  error: string | null;
  recipe_count: number;
  progress_current: number;
  progress_total: number;
  phase: string | null;
  created_at: string;
  processed_at: string | null;
  recipes?: RecipeSummary[];
}

export interface LLMStatus {
  available: boolean;
  provider: string;
  model: string;
  base_url: string;
}
