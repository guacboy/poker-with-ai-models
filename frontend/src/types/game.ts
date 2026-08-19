export type PlayerKind = "human" | "ai";
export type PlayerStatus = "active" | "eliminated";

export interface PublicPlayer {
  player_id: string;
  name: string;
  kind: PlayerKind;
  stack: number;
  status: PlayerStatus;
  buy_ins_used: number;
  buy_ins_remaining: number;
}

export interface PublicSeat {
  player_id: string;
  name: string;
  kind: PlayerKind;
  stack: number;
  bet: number;
  folded: boolean;
  buy_ins_used: number;
  buy_ins_remaining: number;
  is_button: boolean;
  is_small_blind: boolean;
  is_big_blind: boolean;
  is_to_act: boolean;
  hole_cards: string[] | null;
}

export interface PublicHand {
  board_cards: string[];
  pot_total: number;
  street_index: number | null;
  is_over: boolean;
  current_actor_id: string | null;
  seats: PublicSeat[];
}

export interface PublicState {
  hand_count: number;
  blind_level: number;
  small_blind: number;
  big_blind: number;
  hands_until_next_level: number;
  is_over: boolean;
  winner_player_id: string | null;
  players: PublicPlayer[];
  hand: PublicHand | null;
}

export interface LegalActions {
  can_fold: boolean;
  can_check_or_call: boolean;
  can_bet_or_raise: boolean;
  call_amount: number;
  min_bet_to: number | null;
  max_bet_to: number | null;
}

export interface ActorView {
  your_player_id: string;
  your_hole_cards: string[];
  board_cards: string[];
  pot_total: number;
  street_index: number | null;
  small_blind: number;
  big_blind: number;
  seats: PublicSeat[];
  legal_actions: LegalActions;
}

export type ActionName = "fold" | "check_or_call" | "bet_or_raise_to";

export interface BustEvent {
  player_id: string;
  eliminated: boolean;
}

export type ServerEvent =
  | { type: "snapshot"; state: PublicState }
  | { type: "hand_started"; state: PublicState }
  | { type: "awaiting_action"; view: ActorView }
  | {
      type: "player_action";
      player_id: string;
      action: ActionName;
      amount: number | null;
      call_amount: number;
      message: string | null;
      audio_base64: string | null;
      audio_duration: number | null;
      state: PublicState;
    }
  | {
      type: "hand_result";
      net_results: Record<string, number>;
      winners: string[];
      bust_events: BustEvent[];
      state: PublicState;
    }
  | { type: "tournament_over"; winner_player_id: string | null }
  | { type: "error"; message: string };
