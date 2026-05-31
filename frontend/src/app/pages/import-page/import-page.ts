import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { interval, Subscription } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../../api.service';
import { ConfirmService } from '../../confirm.service';
import { ImportJob, LLMStatus, Recipe } from '../../models';
import { SettingsService, formatQty } from '../../settings.service';
import { ToastService } from '../../toast.service';

@Component({
  selector: 'app-import-page',
  imports: [NgTemplateOutlet],
  templateUrl: './import-page.html',
  styleUrl: './import-page.scss',
})
export class ImportPage implements OnInit, OnDestroy {
  api = inject(ApiService);
  private confirm = inject(ConfirmService);
  private settings = inject(SettingsService);
  private toast = inject(ToastService);
  private pollSub?: Subscription;
  private jobPollSub?: Subscription;

  private phaseStartTimes = new Map<string, number>();
  private etaCache = new Map<string, string>();
  private etaLastUpdate = new Map<string, number>();

  llm = signal<LLMStatus | null>(null);
  jobs = signal<ImportJob[]>([]);
  uploading = signal(false);
  processing = signal(false);
  retrying = signal<number | null>(null);
  aborting = signal<number | null>(null);
  expandedJob = signal<number | null>(null);
  expandedRecipe = signal<number | null>(null);
  recipeDetails = signal<Map<number, Recipe>>(new Map());
  uploadError = signal('');
  dragOver = signal(false);
  processedExpanded = signal(false);

  activeJobs = computed(() => this.jobs().filter(j => j.status === 'pending' || j.status === 'processing'));
  processedJobs = computed(() => this.jobs().filter(j => j.status === 'completed' || j.status === 'failed'));

  ngOnInit() {
    this.refresh();
    // Poll LLM status + jobs every 5 s
    this.pollSub = interval(5000).pipe(switchMap(() => this.api.getLLMStatus())).subscribe(s => this.llm.set(s));
    this.jobPollSub = interval(5000).pipe(switchMap(() => this.api.getJobs())).subscribe(newJobs => {
      newJobs.forEach(j => {
        this.updateEta(j);
        if (j.status === 'completed' || j.status === 'failed') this.clearPhaseStorage(j.id);
      });
      this.jobs.update(current => newJobs.map(j => {
        const existing = current.find(c => c.id === j.id);
        return existing?.recipes ? { ...j, recipes: existing.recipes } : j;
      }));
    });
  }

  ngOnDestroy() {
    this.pollSub?.unsubscribe();
    this.jobPollSub?.unsubscribe();
  }

  private refresh() {
    this.api.getLLMStatus().subscribe(s => this.llm.set(s));
    this.api.getJobs().subscribe(j => this.jobs.set(j));
  }

  onDragOver(e: DragEvent) { e.preventDefault(); this.dragOver.set(true); }
  onDragLeave() { this.dragOver.set(false); }

  onDrop(e: DragEvent) {
    e.preventDefault();
    this.dragOver.set(false);
    const files = Array.from(e.dataTransfer?.files ?? []);
    files.forEach(f => this.upload(f));
  }

  onFileChange(e: Event) {
    const files = Array.from((e.target as HTMLInputElement).files ?? []);
    files.forEach(f => this.upload(f));
  }

  private upload(file: File) {
    this.uploading.set(true);
    this.uploadError.set('');
    this.api.uploadFile(file).subscribe({
      next: () => { this.uploading.set(false); this.refresh(); },
      error: err => {
        this.uploading.set(false);
        this.uploadError.set(err.error?.detail ?? 'Upload failed');
      },
    });
  }

  processAll() {
    this.processing.set(true);
    this.api.processPending().subscribe({
      next: () => { this.processing.set(false); this.refresh(); },
      error: err => {
        this.processing.set(false);
        this.toast.show(err.error?.detail ?? 'Could not start processing', 'error');
      },
    });
  }

  expandJob(id: number) {
    if (this.expandedJob() === id) {
      this.expandedJob.set(null);
    } else {
      this.expandedJob.set(id);
      this.api.getJob(id).subscribe(j => {
        this.jobs.update(jobs => jobs.map(jj => jj.id === id ? j : jj));
      });
    }
  }

  toggleRecipe(id: number) {
    if (this.expandedRecipe() === id) {
      this.expandedRecipe.set(null);
      return;
    }
    this.expandedRecipe.set(id);
    if (!this.recipeDetails().has(id)) {
      this.api.getRecipe(id).subscribe(r => {
        this.recipeDetails.update(m => new Map(m).set(id, r));
      });
    }
  }

  abort(jobId: number) {
    this.aborting.set(jobId);
    this.api.abortJob(jobId).subscribe({
      next: () => { this.aborting.set(null); this.refresh(); },
      error: err => {
        this.aborting.set(null);
        this.toast.show(err.error?.detail ?? 'Could not abort job', 'error');
      },
    });
  }

  retry(jobId: number) {
    this.retrying.set(jobId);
    this.api.retryJob(jobId).subscribe({
      next: () => { this.retrying.set(null); this.refresh(); },
      error: err => {
        this.retrying.set(null);
        this.toast.show(err.error?.detail ?? 'Could not retry job', 'error');
      },
    });
  }

  async deleteJob(job: ImportJob) {
    const recipeNote = job.recipe_count > 0
      ? ` This will also remove ${job.recipe_count} recipe(s), including any already accepted into your library.`
      : '';
    if (!await this.confirm.confirm(`Remove this import?${recipeNote}`)) return;
    this.api.deleteJob(job.id).subscribe(() => {
      this.jobs.update(jobs => jobs.filter(j => j.id !== job.id));
      if (this.expandedJob() === job.id) this.expandedJob.set(null);
    });
  }

  readonly PHASES = ['segmenting', 'extracting'] as const;

  phaseStatus(job: ImportJob, phase: string): 'waiting' | 'active' | 'done' {
    if (job.status !== 'processing') return 'waiting';
    const current = this.PHASES.indexOf(job.phase as any);
    const target = this.PHASES.indexOf(phase as any);
    if (current === -1) return target === 0 ? 'active' : 'waiting';
    if (target < current) return 'done';
    if (target === current) return 'active';
    return 'waiting';
  }

  phaseProgress(job: ImportJob, phase: string): number {
    const s = this.phaseStatus(job, phase);
    if (s === 'done') return 100;
    if (s === 'active' && job.progress_total > 0)
      return job.progress_current / job.progress_total * 100;
    return 0;
  }

  phaseCountLabel(job: ImportJob, phase: string): string {
    const s = this.phaseStatus(job, phase);
    if (s === 'done') return '✓';
    if (s === 'waiting') return '–';
    if (job.progress_total > 0) {
      const count = `${job.progress_current} / ${job.progress_total}`;
      if (s === 'active') {
        const eta = this.etaCache.get(`${job.id}:${phase}`) ?? '';
        return eta ? `${count} · ${eta}` : count;
      }
      return count;
    }
    return '…';
  }

  private updateEta(job: ImportJob): void {
    if (job.status !== 'processing' || !job.phase) return;
    const key = `${job.id}:${job.phase}`;
    const lsKey = `mp:ps:${job.id}:${job.phase}`;
    const now = Date.now();

    if (!this.phaseStartTimes.has(key)) {
      const stored = localStorage.getItem(lsKey);
      if (stored) {
        this.phaseStartTimes.set(key, parseInt(stored, 10));
      } else {
        this.phaseStartTimes.set(key, now);
        localStorage.setItem(lsKey, String(now));
      }
    }

    const lastUpdate = this.etaLastUpdate.get(key) ?? 0;
    if (now - lastUpdate < 1000) return;
    this.etaLastUpdate.set(key, now);

    const elapsed = now - this.phaseStartTimes.get(key)!;
    const { progress_current: cur, progress_total: total } = job;

    if (cur <= 0 || total <= 0 || elapsed < 5000) {
      this.etaCache.set(key, '');
      return;
    }

    const remaining = (total - cur) * (elapsed / cur);
    this.etaCache.set(key, this.fmtDuration(remaining) + ' remaining');
  }

  private clearPhaseStorage(jobId: number): void {
    this.PHASES.forEach(phase => localStorage.removeItem(`mp:ps:${jobId}:${phase}`));
  }

  private fmtDuration(ms: number): string {
    const s = Math.round(ms / 1000);
    if (s < 60) return `~${s}s`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    if (m < 60) return `~${m}m ${rem}s`;
    const h = Math.floor(m / 60);
    return `~${h}h ${Math.floor(m % 60)}m`;
  }

  hasPending(): boolean {
    return this.jobs().some(j => j.status === 'pending');
  }

  formatDate(iso: string): string {
    return this.settings.formatDate(iso);
  }

  formatQty = formatQty;
}
