export type PersonStatus = "identified" | "researching" | "synthesizing" | "complete";

export interface WorkHistoryEntry {
  role: string;
  company: string;
  period?: string;
}

export interface EducationEntry {
  school: string;
  degree?: string;
}

export interface SocialProfiles {
  linkedin?: string;
  twitter?: string;
  instagram?: string;
  github?: string;
  website?: string;
}

export interface Dossier {
  summary: string;
  title?: string;
  company?: string;
  workHistory: WorkHistoryEntry[];
  education: EducationEntry[];
  socialProfiles: SocialProfiles;
  notableActivity: string[];
  conversationHooks: string[];
  riskFlags: string[];
}

export interface BoardPosition {
  x: number;
  y: number;
}

export interface PersonRecord {
  _id: string;
  name: string;
  photoUrl: string;
  confidence: number;
  status: PersonStatus;
  boardPosition: BoardPosition;
  dossier?: Dossier;
}

export interface ConnectionRecord {
  _id: string;
  personAId: string;
  personBId: string;
  relationshipType: string;
  description: string;
}

export interface ActivityRecord {
  _id: string;
  type: string;
  message: string;
  personId?: string;
  agentName?: string;
  timestamp: number;
}

// IntelBoard v5 types
export type IntelPersonStatus = "complete" | "scanning" | "inactive";

export type IntelSourceSessionStatus = "pending" | "running" | "completed" | "failed";

export interface IntelSource {
  nm: string;
  tp: string;
  sn: string;
  url?: string;
  sessionId?: string;
  taskId?: string;
  liveUrl?: string;
  shareUrl?: string;
  sessionStatus?: IntelSourceSessionStatus;
}

export interface IntelSummary {
  nm: string;
  sm: string;
  title?: string;
  location?: string;
}

export interface IntelPerson {
  id: string;
  name: string;
  photoUrl?: string;
  status: IntelPersonStatus;
  summary: IntelSummary;
  sources: IntelSource[];
  dossier?: Dossier;
}
