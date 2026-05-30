import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { interval, Subscription } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../../api.service';
import { ImportJob, LLMStatus } from '../../models';

@Component({
  selector: 'app-import-page',
  imports: [NgTemplateOutlet],
  templateUrl: './import-page.html',
  styleUrl: './import-page.scss',
})
export class ImportPage implements OnInit, OnDestroy {
  private api = inject(ApiService);
  private pollSub?: Subscription;
  private jobPollSub?: Subscription;

  llm = signal<LLMStatus | null>(null);
  jobs = signal<ImportJob[]>([]);
  uploading = signal(false);
  processing = signal(false);
  retrying = signal<number | null>(null);
  expandedJob = signal<number | null>(null);
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
        alert(err.error?.detail ?? 'Could not start processing');
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

  acceptAll(jobId: number) {
    this.api.acceptJob(jobId).subscribe(() => {
      this.refresh();
      this.api.getJob(jobId).subscribe(j => this.jobs.update(jobs => jobs.map(jj => jj.id === jobId ? j : jj)));
    });
  }

  acceptOne(jobId: number, recipeId: number) {
    this.api.acceptJob(jobId, [recipeId]).subscribe(() => {
      this.api.getJob(jobId).subscribe(j => this.jobs.update(jobs => jobs.map(jj => jj.id === jobId ? j : jj)));
    });
  }

  retry(jobId: number) {
    this.retrying.set(jobId);
    this.api.retryJob(jobId).subscribe({
      next: () => { this.retrying.set(null); this.refresh(); },
      error: err => {
        this.retrying.set(null);
        alert(err.error?.detail ?? 'Could not retry job');
      },
    });
  }

  deleteJob(job: ImportJob) {
    const recipeNote = job.recipe_count > 0
      ? ` This will also remove ${job.recipe_count} recipe(s), including any already accepted into your library.`
      : '';
    if (!confirm(`Remove this import?${recipeNote}`)) return;
    this.api.deleteJob(job.id).subscribe(() => {
      this.jobs.update(jobs => jobs.filter(j => j.id !== job.id));
      if (this.expandedJob() === job.id) this.expandedJob.set(null);
    });
  }

  readonly PHASES = ['segmenting', 'extracting', 'verifying'] as const;

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
    if (job.progress_total > 0) return `${job.progress_current} / ${job.progress_total}`;
    return '…';
  }

  hasPending(): boolean {
    return this.jobs().some(j => j.status === 'pending');
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleString();
  }
}
