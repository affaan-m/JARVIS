"use client";

import { motion } from "framer-motion";
import { User, Briefcase, MapPin } from "lucide-react";
import Image from "next/image";

import type { PersonRecord } from "@/lib/types";

interface PersonCardProps {
  person: PersonRecord;
  isSelected: boolean;
  onClick: () => void;
}

const statusColors: Record<string, string> = {
  identified: "var(--status-pending)",
  researching: "var(--status-researching)",
  synthesizing: "var(--alert-amber)",
  complete: "var(--status-complete)",
};

const statusLabels: Record<string, string> = {
  identified: "IDENTIFIED",
  researching: "RESEARCHING",
  synthesizing: "SYNTHESIZING",
  complete: "COMPLETE",
};

export function PersonCard({ person, isSelected, onClick }: PersonCardProps) {
  const rotation = ((person.name.charCodeAt(0) % 7) - 3) * 1.5; // -4.5 to 4.5 deg

  return (
    <motion.div
      data-person-card
      initial={{ scale: 0, rotate: rotation - 10, opacity: 0 }}
      animate={{
        scale: 1,
        rotate: rotation,
        opacity: 1,
      }}
      whileHover={{ scale: 1.05, zIndex: 100, rotate: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
      className="absolute cursor-pointer"
      style={{
        left: person.boardPosition.x,
        top: person.boardPosition.y,
        width: 220,
        filter: isSelected ? "drop-shadow(0 0 12px rgba(231, 76, 60, 0.5))" : "drop-shadow(2px 4px 8px rgba(0,0,0,0.4))",
      }}
      onClick={onClick}
    >
      {/* Pushpin */}
      <div
        className="absolute -top-2 left-1/2 -translate-x-1/2 w-4 h-4 rounded-full z-10 border-2"
        style={{
          background: "var(--pin-gold)",
          borderColor: "#b8860b",
          boxShadow: "0 2px 4px rgba(0,0,0,0.5)",
        }}
      />

      {/* Paper card */}
      <div className="paper-texture rounded-sm p-3 relative" style={{ color: "#2a2a2a" }}>
        {/* Status badge */}
        <div
          className="absolute top-2 right-2 text-[9px] px-1.5 py-0.5 rounded tracking-wider font-bold"
          style={{
            background: statusColors[person.status],
            color: "#fff",
            fontFamily: "var(--font-mono)",
          }}
        >
          {statusLabels[person.status]}
        </div>

        {/* Photo */}
        <div className="w-16 h-20 mx-auto mb-2 overflow-hidden border-2 border-gray-300" style={{ background: "#ddd" }}>
          {person.photoUrl ? (
            <Image
              src={person.photoUrl}
              alt={person.name}
              width={64}
              height={80}
              className="w-full h-full object-cover"
              unoptimized
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <User className="w-8 h-8 text-gray-400" />
            </div>
          )}
        </div>

        {/* Name */}
        <h3
          className="text-center text-lg leading-tight"
          style={{ fontFamily: "var(--font-heading)", letterSpacing: "2px" }}
        >
          {person.name.toUpperCase()}
        </h3>

        {/* Title & Company */}
        {person.dossier?.title && (
          <div className="flex items-center gap-1 justify-center mt-1 text-[10px] text-gray-600">
            <Briefcase className="w-3 h-3" />
            <span style={{ fontFamily: "var(--font-mono)" }}>
              {person.dossier.title}
            </span>
          </div>
        )}

        {person.dossier?.company && (
          <div className="flex items-center gap-1 justify-center mt-0.5 text-[10px] text-gray-600">
            <MapPin className="w-3 h-3" />
            <span style={{ fontFamily: "var(--font-mono)" }}>
              {person.dossier.company}
            </span>
          </div>
        )}

        {/* Confidence bar */}
        <div className="mt-2 h-1 bg-gray-300 rounded-full overflow-hidden">
          <motion.div
            className="h-full rounded-full"
            style={{ background: "var(--intel-green)" }}
            initial={{ width: 0 }}
            animate={{ width: `${person.confidence * 100}%` }}
            transition={{ duration: 1, delay: 0.3 }}
          />
        </div>

        {/* Classified stamp for complete persons */}
        {person.status === "complete" && (
          <motion.div
            className="absolute bottom-2 right-2 classified-stamp text-[10px] py-0.5 px-2"
            initial={{ scale: 2, opacity: 0 }}
            animate={{ scale: 1, opacity: 0.7 }}
            transition={{ type: "spring", stiffness: 500, damping: 15, delay: 0.5 }}
          >
            FILED
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
