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
