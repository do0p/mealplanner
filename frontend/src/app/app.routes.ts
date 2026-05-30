import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: '/recipes', pathMatch: 'full' },
  {
    path: 'recipes',
    loadComponent: () => import('./pages/recipes/recipes').then(m => m.RecipesPage),
  },
  {
    path: 'recipes/:id',
    loadComponent: () => import('./pages/recipe-detail/recipe-detail').then(m => m.RecipeDetailPage),
  },
  {
    path: 'import',
    loadComponent: () => import('./pages/import-page/import-page').then(m => m.ImportPage),
  },
  {
    path: 'planner',
    loadComponent: () => import('./pages/planner/planner').then(m => m.PlannerPage),
  },
  {
    path: 'shopping-list/:planId',
    loadComponent: () =>
      import('./pages/shopping-list/shopping-list').then(m => m.ShoppingListPage),
  },
];
