"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { ExternalLink, X } from "lucide-react";

import type { PersonRecord } from "@/lib/types";

interface DossierViewProps {
  person: PersonRecord;
  onClose: () => void;
}

const panelVariants = {
  hidden: { x: 400, opacity: 0 },
  visible: {
    x: 0,
    opacity: 1,
    transition: { type: "spring" as const, stiffness: 300, damping: 30 },
  },
  exit: {
    x: 400,
    opacity: 0,
    transition: { duration: 0.25, ease: "easeIn" as const },
  },
};

const contentStagger = {
  visible: {
    transition: { staggerChildren: 0.08, delayChildren: 0.2 },
  },
};

const sectionVariant = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: "easeOut" as const },
  },
};

export function DossierView({ person, onClose }: DossierViewProps) {
  const dossier = person.dossier;

  return (
      <motion.aside
        data-testid="dossier-view"
        className="w-[360px] shrink-0 border-l px-5 py-4 overflow-y-auto"
        style={{
          background: "linear-gradient(180deg, rgba(20,26,18,0.98), rgba(12,16,10,0.98))",
          borderColor: "rgba(200,214,176,0.12)",
        }}
        variants={panelVariants}
        initial="hidden"
        animate="visible"
        exit="exit"
      >
        <motion.div
          className="mb-5 flex items-start justify-between gap-3"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.3 }}
        >
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
          <motion.button
            aria-label="Close dossier"
            data-testid="close-dossier"
            className="rounded-full border p-2 transition hover:opacity-80"
            style={{ borderColor: "rgba(200,214,176,0.12)" }}
            onClick={onClose}
            whileHover={{ rotate: 90 }}
            transition={{ duration: 0.2 }}
          >
            <X className="h-4 w-4" />
          </motion.button>
        </motion.div>

        <motion.section
          className="space-y-5 text-sm"
          variants={contentStagger}
          initial="hidden"
          animate="visible"
        >
          <motion.div variants={sectionVariant}>
            <Block title="Summary">
              <p className="leading-6">{dossier?.summary ?? "No synthesized dossier yet."}</p>
            </Block>
          </motion.div>

          <motion.div variants={sectionVariant}>
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
          </motion.div>

          <motion.div variants={sectionVariant}>
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
          </motion.div>

          <motion.div variants={sectionVariant}>
            <Block title="Conversation Hooks">
              <ul className="space-y-2">
                {(dossier?.conversationHooks ?? []).map((hook) => (
                  <li key={hook}>• {hook}</li>
                ))}
              </ul>
            </Block>
          </motion.div>

          <motion.div variants={sectionVariant}>
            <Block title="Risk Flags">
              <ul className="space-y-2">
                {(dossier?.riskFlags ?? []).length ? (
                  dossier?.riskFlags.map((flag) => <li key={flag}>• {flag}</li>)
                ) : (
                  <li style={{ color: "var(--text-dim)" }}>No active flags.</li>
                )}
              </ul>
            </Block>
          </motion.div>

          <motion.div variants={sectionVariant}>
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
          </motion.div>
        </motion.section>
      </motion.aside>
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
