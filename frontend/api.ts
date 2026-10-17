import type {
  Case,
  Capabilities,
  Activity,
  Sample,
  RecentCase,
  Artifact,
  Provider,
  ReviewStatus,
} from "./types";
import type { components } from "./generated-api";

const base = "/api/v1";
export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(base + path, {
    credentials: "same-origin",
    ...init,
    headers: {
      ...(init.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
    } catch {
      /* use status */
    }
    throw new Error(detail);
  }
  return response.json();
}
export const api = {
  capabilities: () => request<Capabilities>("/capabilities"),
  samples: () => request<Sample[]>("/samples"),
  recent: () => request<RecentCase[]>("/cases"),
  create: (provider: Provider) =>
    request<Case>("/cases", {
      method: "POST",
      body: JSON.stringify({
        provider,
        title: "Untitled investigation",
      } satisfies components["schemas"]["CaseCreate"]),
    }),
  case: (id: string) => request<Case>(`/cases/${id}`),
  sample: (id: string, kind: string) =>
    request<Case>(`/cases/${id}/sample/${kind}`, { method: "POST" }),
  github: (id: string, url: string) =>
    request(`/cases/${id}/sources/github`, {
      method: "POST",
      body: JSON.stringify({
        url,
      } satisfies components["schemas"]["GithubSource"]),
    }),
  start: (id: string) => request(`/cases/${id}/start`, { method: "POST" }),
  decision: (id: string, question_id: string, answer: string) =>
    request(`/cases/${id}/decisions`, {
      method: "POST",
      body: JSON.stringify({
        question_id,
        answer,
        rationale: "",
      } satisfies components["schemas"]["DecisionInput"]),
    }),
  review: (id: string, finding: string, status: ReviewStatus, note: string) =>
    request(`/cases/${id}/findings/${finding}/review`, {
      method: "POST",
      body: JSON.stringify({
        status,
        note,
      } satisfies components["schemas"]["ReviewInput"]),
    }),
  rerun: (id: string) => request(`/cases/${id}/rerun`, { method: "POST" }),
  cancel: (id: string) => request(`/cases/${id}/cancel`, { method: "POST" }),
  remove: (id: string) => request(`/cases/${id}`, { method: "DELETE" }),
  artifact: (id: string, artifact: string) =>
    request<Artifact>(`/cases/${id}/artifacts/${artifact}`),
  upload: (id: string, file: File, progress: (value: number) => void) =>
    new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", base + `/cases/${id}/artifacts`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable)
          progress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else {
          try {
            reject(new Error(JSON.parse(xhr.responseText).detail));
          } catch {
            reject(new Error("Upload failed"));
          }
        }
      };
      xhr.onerror = () =>
        reject(new Error("Connection interrupted during upload"));
      const data = new FormData();
      data.append("file", file);
      xhr.send(data);
    }),
  events: (id: string, receive: (event: Activity) => void) => {
    const source = new EventSource(base + `/cases/${id}/events`);
    source.onmessage = (e) => receive(JSON.parse(e.data));
    return () => source.close();
  },
  exportUrl: (id: string, format: string) =>
    base + `/cases/${id}/exports/${format}`,
};
