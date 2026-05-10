// Wargamer-mode shared types. Used by api.ts (the live client),
// components.tsx, and OrdersPanel.tsx. Static fixtures from the
// Claude Design prototype have been removed now that the page is
// API-driven.

export interface TurnLogEntry {
  turn: number;
  time: string;
  model: string;
  status: string;
  intent: string;
  current?: boolean;
}

export interface OrderSection {
  n: string;
  title: string;
  body: string[];
}

export interface OrdersData {
  see_board: string[];
  unread: string;
  sections: OrderSection[];
  ack: string;
}
