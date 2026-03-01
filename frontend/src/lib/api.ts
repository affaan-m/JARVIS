const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface CaptureResult {
  capture_id: string;
  filename: string;
  content_type: string;
  status: "queued" | "processed" | "error";
  source: string;
  total_frames?: number;
  faces_detected?: number;
  persons_created?: number;
  error?: string;
}

export interface ServiceStatus {
  name: string;
  configured: boolean;
  notes: string | null;
}

export interface HealthResponse {
  status: "ok";
  environment: string;
  services: Record<string, boolean>;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function uploadCapture(file: File): Promise<CaptureResult> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<CaptureResult>("/api/capture", {
    method: "POST",
    body: form,
  });
}

export async function getServices(): Promise<ServiceStatus[]> {
  return apiFetch<ServiceStatus[]>("/api/services");
}

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/health");
}
