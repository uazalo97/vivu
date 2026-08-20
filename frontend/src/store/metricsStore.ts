import { create } from "zustand";
import {
  fetchOverview,
  fetchTimeseries,
  fetchIntents,
  fetchLogs,
  fetchRealtime,
  type MetricsOverview,
  type TimeseriesPoint,
  type IntentItem,
  type LogRow,
  type RealtimePoint,
} from "../api/metrics";

type State = {
  hours: number;
  realtimeWindow: number;
  overview: MetricsOverview | null;
  timeseries: TimeseriesPoint[];
  intents: IntentItem[];
  realtime: RealtimePoint[];
  logs: LogRow[];
  logsTotal: number;
  loading: boolean;
  error: string | null;
  setHours: (h: number) => void;
  refresh: () => Promise<void>;
};

export const useMetricsStore = create<State>((set, get) => ({
  hours: 24,
  realtimeWindow: 5,
  overview: null,
  timeseries: [],
  intents: [],
  realtime: [],
  logs: [],
  logsTotal: 0,
  loading: false,
  error: null,
  setHours: (h) => set({ hours: h }),
  refresh: async () => {
    const { hours, realtimeWindow } = get();
    set({ loading: true, error: null });
    try {
      const [ov, ts, it, lg, rt] = await Promise.all([
        fetchOverview(hours),
        fetchTimeseries(hours),
        fetchIntents(hours),
        fetchLogs({ limit: 50 }),
        fetchRealtime(realtimeWindow),
      ]);
      set({
        overview: ov,
        timeseries: ts.points || [],
        intents: it.intents || [],
        logs: lg.logs || [],
        logsTotal: lg.total || 0,
        realtime: rt.points || [],
        loading: false,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg, loading: false });
    }
  },
}));
