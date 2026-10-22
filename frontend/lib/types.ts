// docs/API.md 의 모양. 모르는 필드는 무시한다.
export type SessionSummary = { id: string; title: string; updated_at: string };

export type TracePlace = { name: string; address?: string; map_link?: string };

export type TraceStay = {
  gid: number;
  name: string;
  description?: string;
  price?: string;
  price_with_tax?: string;
  rating?: number | null;
  review_count?: string;
  tags?: string[];
  image?: string;
  booking_link: string;
};

export type PlaceInfo = {
  name: string;
  kind?: string;
  status: "found" | "not_found" | "error";
  weekly_hours?: Record<string, string | null> | null;
  by_date?: Record<string, string>;
  closed_note?: string | null;
  menu?: { name: string; price?: string | null }[];
  notes?: string | null;
  sources?: { title: string; url: string }[];
};

export type TraceStep = {
  step: number;
  tool: string;
  args?: Record<string, unknown>;
  status: string;
  note?: string;
  count?: number;
  places?: TracePlace[];
  stays?: TraceStay[];
  infos?: PlaceInfo[];
  source?: string;
  queried_at?: string;
  result?: Record<string, unknown>;
  warnings?: string[];
};

export type Trace = {
  steps: TraceStep[];
  tool_calls?: number;
  tool_limit?: number;
  model_calls?: number;
  model_limit?: number;
  end?: string;
  grounded?: boolean;
};

export type DraftPlace = {
  name: string;
  address?: string;
  map_link?: string;
  lat?: number;
  lon?: number;
};

export type Draft = {
  cond: { region?: string; date?: string; preference?: string };
  warnings: string[];
  places: DraftPlace[];
  weather_source?: string;
  weather_state?: string;
  packing: string[];
  time_slots: string[];
};

export type FoodPlace = {
  id?: string;
  name: string;
  address?: string;
  map_link?: string;
  category?: string;
  distance_m?: number;
  lat?: number;
  lon?: number;
};

export type FoodMeal = { meal: string; anchor?: string; place: FoodPlace | null };
export type FoodDay = { day: number; date: string; weekday: string; meals: FoodMeal[] };
export type Food = {
  request: { start_date: string; days: number; departure: string; return_time: string };
  days: FoodDay[];
  total_meals?: number;
  picked?: FoodPlace[];
  failed?: boolean;
  notes: string[];
};

export type FoodRequest = Food["request"];

export type UserMessage = { role: "user"; content: string; error?: boolean };
export type AssistantMessage = {
  role: "assistant";
  content: string;
  question?: string;
  trace?: Trace | null;
  offer: false | "draft" | "food" | "plan";
  offer_defaults?: { start_date?: string } | null;
  draft: Draft | null;
  food: Food | null;
  error?: boolean;
};
export type Message = UserMessage | AssistantMessage;

export type SessionDetail = SessionSummary & { messages: Message[] };
