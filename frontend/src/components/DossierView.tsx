"use client";

import type { ReactNode } from "react";
import { ExternalLink, X } from "lucide-react";

import type { PersonRecord } from "@/lib/types";

interface DossierViewProps {
  person: PersonRecord;
  onClose: () => void;
}

export function DossierView({ person, onClose }: DossierViewProps) {
  const dossier = person.dossier;

  return (
    <aside
      className="w-[360px] shrink-0 border-l px-5 py-4 overflow-y-auto"
      style={{
        background: "linear-gradient(180deg, rgba(20,26,18,0.98), rgba(12,16,10,0.98))",
        borderColor: "rgba(200,214,176,0.12)",
      }}
    >
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <p
            className="text-xs tracking-[0.35em]"
            style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)" }}
          >
            DOSSIER
          </p>
          <h2
            className="text-3xl leading-none"
            style={{ fontFamily: "var(--font-heading)", letterSpacing: "0.14em" }}
          >
            {person.name}
          </h2>
          <p className="mt-2 text-sm" style={{ color: "var(--text-dim)" }}>
            {(dossier?.title ?? "Unknown role") + (dossier?.company ? ` // ${dossier.company}` : "")}
          </p>
        </div>
        <button
          aria-label="Close dossier"
          className="rounded-full border p-2 transition hover:opacity-80"
          style={{ borderColor: "rgba(200,214,176,0.12)" }}
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <section className="space-y-5 text-sm">
        <Block title="Summary">
          <p className="leading-6">{dossier?.summary ?? "No synthesized dossier yet."}</p>
        </Block>

        <Block title="Work History">
          <ul className="space-y-2">
            {(dossier?.workHistory ?? []).map((entry) => (
              <li key={`${entry.company}-${entry.role}`}>
                <strong>{entry.role}</strong>
                {" // "}
                {entry.company}
                {entry.period ? <span style={{ color: "var(--text-dim)" }}>{" // "}{entry.period}</span> : null}
              </li>
            ))}
          </ul>
        </Block>

        <Block title="Education">
          <ul className="space-y-2">
            {(dossier?.education ?? []).map((entry) => (
              <li key={`${entry.school}-${entry.degree ?? "unknown"}`}>
                <strong>{entry.school}</strong>
                {entry.degree ? <span style={{ color: "var(--text-dim)" }}>{" // "}{entry.degree}</span> : null}
              </li>
            ))}
          </ul>
        </Block>

        <Block title="Conversation Hooks">
          <ul className="space-y-2">
            {(dossier?.conversationHooks ?? []).map((hook) => (
              <li key={hook}>• {hook}</li>
            ))}
          </ul>
        </Block>

        <Block title="Risk Flags">
          <ul className="space-y-2">
            {(dossier?.riskFlags ?? []).length ? (
              dossier?.riskFlags.map((flag) => <li key={flag}>• {flag}</li>)
            ) : (
              <li style={{ color: "var(--text-dim)" }}>No active flags.</li>
            )}
          </ul>
        </Block>

        <Block title="Links">
          <div className="space-y-2">
            {Object.entries(dossier?.socialProfiles ?? {}).map(([key, value]) =>
              value ? (
                <a
                  key={key}
                  className="flex items-center gap-2 hover:underline"
                  href={buildProfileUrl(key, value)}
                  rel="noreferrer"
                  target="_blank"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  <span>{key.toUpperCase()}</span>
                </a>
              ) : null
            )}
          </div>
        </Block>
      </section>
    </aside>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3
        className="mb-2 text-xl"
        style={{ fontFamily: "var(--font-heading)", letterSpacing: "0.12em" }}
      >
        {title}
      </h3>
      <div
        className="rounded-sm border px-3 py-3"
        style={{
          borderColor: "rgba(200,214,176,0.1)",
          background: "rgba(255,255,255,0.02)",
        }}
      >
        {children}
      </div>
    </section>
  );
}

function buildProfileUrl(key: string, value: string) {
  if (value.startsWith("http")) {
    return value;
  }
  if (key === "twitter" && value.startsWith("@")) {
    return `https://x.com/${value.slice(1)}`;
  }
  return `https://${value}`;
}
