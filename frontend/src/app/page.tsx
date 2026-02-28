"use client";

import { useState } from "react";

import { Corkboard } from "@/components/Corkboard";
import { DossierView } from "@/components/DossierView";
import { LiveFeed } from "@/components/LiveFeed";
import { StatusBar } from "@/components/StatusBar";
import { TopBar } from "@/components/TopBar";
import { demoActivity, demoConnections, demoPersons } from "@/lib/demo-data";

export default function Home() {
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(demoPersons[0]?._id ?? null);

  const selectedPerson = demoPersons.find((person) => person._id === selectedPersonId) ?? null;

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col" style={{ background: "var(--bg-dark)" }}>
      <TopBar personCount={demoPersons.length} />

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 relative">
          <Corkboard
            persons={demoPersons}
            connections={demoConnections}
            onPersonClick={(id) => setSelectedPersonId(id)}
            selectedPersonId={selectedPersonId}
          />
        </div>

        <LiveFeed activity={demoActivity} onEventClick={(personId) => setSelectedPersonId(personId ?? null)} />

        {selectedPerson && (
          <DossierView
            person={selectedPerson}
            onClose={() => setSelectedPersonId(null)}
          />
        )}
      </div>

      <StatusBar persons={demoPersons} />
    </div>
  );
}
