export enum RiskLevel {
  LOW = 'LOW',
  MEDIUM = 'MEDIUM',
  HIGH = 'HIGH',
  CRITICAL = 'CRITICAL'
}

export type AgentStatus = 'idle' | 'parsing' | 'reasoning' | 'reviewing';

export interface Document {
  id: string;
  name: string;
  type: 'PDF' | 'Excel' | 'Image';
  uploadDate: string;
  status: 'QUEUED' | 'PARSING' | 'COMPLETED' | 'ERROR';
  riskLevel: RiskLevel;
  confidence: number;
}

export interface RiskAlert {
  id: string;
  title: string;
  description: string;
  timestamp: string;
  level: RiskLevel;
  relatedDocs: string[];
  dimension: 'Financial' | 'Legal' | 'Operational' | 'Compliance';
}

export interface EntityNode {
  id: string;
  label: string;
  type: 'Company' | 'Person' | 'Contract' | 'Location' | 'Risk' | 'Rating' | '合同' | '风险' | '评分';
  x: number;
  y: number;
}

export interface EntityLink {
  source: string;
  target: string;
  label: string;
}

export interface TableRow {
  id: string;
  item: string;
  amount: number;
  date: string;
  sourceDoc: string;
  confidence: number;
  status: 'VERIFIED' | 'MISMATCH' | 'PENDING';
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}