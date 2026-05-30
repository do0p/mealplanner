import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';
import {
  ImportJob,
  LLMStatus,
  Plan,
  PlanSummary,
  Recipe,
  RecipeSummary,
  ShoppingList,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = environment.apiUrl;

  // ── Recipes ──────────────────────────────────────────────────────────────
  getRecipes(status = 'accepted'): Observable<RecipeSummary[]> {
    return this.http.get<RecipeSummary[]>(`${this.base}/recipes/?status=${status}`);
  }

  getRecipe(id: number): Observable<Recipe> {
    return this.http.get<Recipe>(`${this.base}/recipes/${id}?status=all`);
  }

  updateRecipe(id: number, data: object): Observable<Recipe> {
    return this.http.put<Recipe>(`${this.base}/recipes/${id}`, data);
  }

  deleteRecipe(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/recipes/${id}`);
  }

  recipeSourceUrl(id: number): string {
    return `${this.base}/recipes/${id}/source`;
  }

  // ── Plans ─────────────────────────────────────────────────────────────────
  getPlans(): Observable<PlanSummary[]> {
    return this.http.get<PlanSummary[]>(`${this.base}/plans/`);
  }

  createPlan(name: string): Observable<Plan> {
    return this.http.post<Plan>(`${this.base}/plans/`, { name });
  }

  getPlan(id: number): Observable<Plan> {
    return this.http.get<Plan>(`${this.base}/plans/${id}`);
  }

  updatePlan(id: number, data: object): Observable<Plan> {
    return this.http.put<Plan>(`${this.base}/plans/${id}`, data);
  }

  deletePlan(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/plans/${id}`);
  }

  getShoppingList(planId: number): Observable<ShoppingList> {
    return this.http.get<ShoppingList>(`${this.base}/plans/${planId}/shopping-list`);
  }

  // ── Imports ───────────────────────────────────────────────────────────────
  getLLMStatus(): Observable<LLMStatus> {
    return this.http.get<LLMStatus>(`${this.base}/imports/llm-status`);
  }

  getJobs(): Observable<ImportJob[]> {
    return this.http.get<ImportJob[]>(`${this.base}/imports/`);
  }

  uploadFile(file: File): Observable<ImportJob> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<ImportJob>(`${this.base}/imports/uploads`, form);
  }

  processPending(): Observable<{ queued: number; job_ids?: number[] }> {
    return this.http.post<{ queued: number }>(`${this.base}/imports/process`, {});
  }

  getJob(id: number): Observable<ImportJob> {
    return this.http.get<ImportJob>(`${this.base}/imports/${id}`);
  }

  acceptJob(jobId: number, recipeIds?: number[]): Observable<{ accepted: number }> {
    return this.http.post<{ accepted: number }>(
      `${this.base}/imports/${jobId}/accept`,
      recipeIds != null ? { recipe_ids: recipeIds } : {}
    );
  }

  retryJob(jobId: number): Observable<{ queued: number; job_ids?: number[] }> {
    return this.http.post<{ queued: number }>(`${this.base}/imports/${jobId}/retry`, {});
  }

  abortJob(jobId: number): Observable<{ aborted: boolean }> {
    return this.http.post<{ aborted: boolean }>(`${this.base}/imports/${jobId}/abort`, {});
  }

  deleteJob(jobId: number): Observable<{ deleted: boolean; accepted_removed: number }> {
    return this.http.delete<{ deleted: boolean; accepted_removed: number }>(`${this.base}/imports/${jobId}`);
  }
}
