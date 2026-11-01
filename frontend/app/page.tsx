"use client";

import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import {
  Archive,
  ArrowUpRight,
  Bell,
  ChefHat,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Home,
  Mic,
  MicOff,
  Package,
  Plus,
  Radio,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Tab = "pantry" | "household" | "voice" | "alerts" | "planner";
type Food = {
  id: number;
  name: string;
  location: string;
  bought_date: string;
  shelf_days: number;
  expiry_date: string;
  days_left: number;
  status: string;
  level: string | null;
};
type Household = {
  id: number;
  name: string;
  category: string;
  location: string;
  recorded_at: string;
};
type Alert = {
  id: number;
  level: string;
  channel: string;
  message: string;
  sent_at: string;
  is_read: boolean;
  delivery_status: string;
};
type Draft = {
  name: string;
  location: string;
  bought_date: string;
  shelf_days: string;
  category: string;
  recorded_at: string;
  clarification: string;
  quantity_text: string;
  expiry_date_hint: string;
};
type LiveResult = {
  kind: string;
  items?: Record<string, unknown>[];
  plan?: Plan;
  commentary: string;
};
type Meal = {
  dish: string;
  items_used: string[];
  steps: string[];
  priority_items: string[];
};
type MealImage = { url: string; source_url: string; source_title: string };
type Plan = {
  priority: string[];
  notice: string | null;
  meals: { breakfast: Meal; lunch: Meal; dinner: Meal };
  sources?: { title: string; url: string }[];
  meal_images?: Partial<
    Record<"breakfast" | "lunch" | "dinner", MealImage | null>
  >;
};
const blank = (): Draft => ({
  name: "",
  location: "",
  bought_date: "",
  shelf_days: "",
  category: "",
  recorded_at: "",
  clarification: "",
  quantity_text: "",
  expiry_date_hint: "",
});
const tabs: { id: Tab; label: string; icon: typeof Home }[] = [
  { id: "pantry", label: "Pantry", icon: Archive },
  { id: "household", label: "Household", icon: Home },
  { id: "voice", label: "Add items", icon: Mic },
  { id: "alerts", label: "Alerts", icon: Bell },
  { id: "planner", label: "Meal planner", icon: ChefHat },
];
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (response.status === 401)
    throw new Error("Please sign in to access your home.");
  if (!response.ok) {
    let msg = "Something went wrong. Please try again.";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") msg = data.detail;
    } catch {}
    throw new Error(msg);
  }
  return response.json();
}
const post = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});
const localTime = (iso: string) => {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
};
function toDraft(input: Record<string, unknown>): Draft {
  const draft = {
    ...blank(),
    ...Object.fromEntries(
      Object.entries(input).map(([k, v]) => [k, v == null ? "" : String(v)]),
    ),
  } as Draft;
  if (draft.recorded_at) {
    const date = new Date(draft.recorded_at);
    if (!Number.isNaN(date.getTime()))
      draft.recorded_at = new Date(
        date.getTime() - date.getTimezoneOffset() * 60000,
      )
        .toISOString()
        .slice(0, 16);
  }
  return draft;
}
function RecipePhoto({ image, dish }: { image: MealImage; dish: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="recipe-photo">
      {!failed && (
        <a
          href={image.source_url}
          target="_blank"
          rel="noreferrer"
          aria-label={`View source for a related ${dish} photo`}
        >
          <img
            src={image.url}
            alt={`Related recipe photo for ${dish}`}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={() => setFailed(true)}
          />
        </a>
      )}
      <a
        className="recipe-photo-source"
        href={image.source_url}
        target="_blank"
        rel="noreferrer"
      >
        {failed ? "Photo unavailable · " : "Related photo · "}
        {image.source_title} ↗
      </a>
    </div>
  );
}

function Field({
  label,
  children,
  full = false,
}: {
  label: string;
  children: React.ReactNode;
  full?: boolean;
}) {
  const id = useId();
  const control = isValidElement(children)
    ? cloneElement(children as React.ReactElement<{ id?: string }>, { id })
    : children;
  return (
    <div className={`field ${full ? "full" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {control}
    </div>
  );
}

export default function Page() {
  const [tab, setTab] = useState<Tab>("pantry");
  const [food, setFood] = useState<Food[]>([]);
  const [home, setHome] = useState<Household[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [notificationStatus, setNotificationStatus] = useState<{
    sms_enabled: boolean;
    sms_number_configured: boolean;
    timezone: string;
    jobs: {
      id: number;
      channel: string;
      status: string;
      scheduled_at: string;
      items: { name: string } | null;
    }[];
  } | null>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [signedOut, setSignedOut] = useState(false);
  const [kind, setKind] = useState<"food" | "household">("food");
  const [transcript, setTranscript] = useState("");
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [editing, setEditing] = useState<{
    kind: "food" | "household";
    id: number;
    draft: Draft;
  } | null>(null);
  const [previewDate, setPreviewDate] = useState("");
  const [preview, setPreview] = useState<Food[] | null>(null);
  const [demoDays, setDemoDays] = useState("0");
  const [demoEvents, setDemoEvents] = useState<
    { channel: string; scheduled_at: string; message: string }[]
  >([]);
  const [demoActive, setDemoActive] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [research, setResearch] = useState(false);
  const [recording, setRecording] = useState(false);
  const [live, setLive] = useState(false);
  const mic = useRef<{
    ws: WebSocket;
    stream: MediaStream;
    ctx: AudioContext;
    node: AudioWorkletNode;
    flushed?: () => void;
  } | null>(null);
  const liveRef = useRef<{
    pc: RTCPeerConnection;
    stream: MediaStream;
    dc: RTCDataChannel;
    audio: HTMLAudioElement;
    history: string;
    userText: string;
    lastUserDelta: number;
    fallbackTimer: ReturnType<typeof setTimeout> | null;
    lastSubmitted: string;
    pendingText: string;
    pendingTask: Promise<LiveResult> | null;
    delegationVersion: number;
    closed: boolean;
  } | null>(null);
  const refresh = useCallback(async () => {
    const [a, b, c, d] = await Promise.allSettled([
      api<Food[]>("/items"),
      api<Household[]>("/household"),
      api<Alert[]>("/alerts"),
      api<{
        sms_enabled: boolean;
        sms_number_configured: boolean;
        timezone: string;
        jobs: {
          id: number;
          channel: string;
          status: string;
          scheduled_at: string;
          items: { name: string } | null;
        }[];
      }>("/notification-status"),
    ]);
    if (a.status === "fulfilled") setFood(a.value);
    if (b.status === "fulfilled") setHome(b.value);
    if (c.status === "fulfilled") setAlerts(c.value);
    if (d.status === "fulfilled") setNotificationStatus(d.value);
    const failure = [a, b, c, d].find((x) => x.status === "rejected");
    if (failure?.status === "rejected") {
      const message = (failure.reason as Error).message;
      setError(message);
      setSignedOut(message.includes("sign in"));
    } else setSignedOut(false);
  }, []);
  useEffect(() => {
    refresh();
    if ("serviceWorker" in navigator)
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    const t = setInterval(refresh, 60000);
    return () => clearInterval(t);
  }, [refresh]);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setInfo("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const draftChange = (idx: number, key: keyof Draft, value: string) =>
    setDrafts((d) =>
      d.map((item, i) => {
        if (i !== idx) return item;
        const updated = { ...item, [key]: value };
        if (
          (key === "bought_date" || key === "expiry_date_hint") &&
          updated.bought_date &&
          updated.expiry_date_hint
        ) {
          const days = Math.round(
            (Date.parse(updated.expiry_date_hint + "T00:00:00Z") -
              Date.parse(updated.bought_date + "T00:00:00Z")) /
              86400000,
          );
          updated.shelf_days =
            Number.isFinite(days) && days >= 0 ? String(days) : "";
        }
        return updated;
      }),
    );
  const parse = () =>
    run(async () => {
      if (!transcript.trim())
        throw new Error("Add a description or record a voice note first.");
      const result = await api<{ items: Record<string, unknown>[] }>(
        kind === "food" ? "/voice" : "/household/extract",
        post({ transcript }),
      );
      setDrafts(result.items.map(toDraft));
      if (!result.items.length)
        setInfo(
          "No items were found. Add an item manually or try another description.",
        );
    });
  const save = () =>
    run(async () => {
      if (!drafts.length) throw new Error("Add at least one item.");
      if (kind === "food") {
        const items = drafts.map((d) => {
          if (
            !d.name.trim() ||
            !d.location ||
            !d.bought_date ||
            d.shelf_days === "" ||
            !Number.isInteger(Number(d.shelf_days)) ||
            Number(d.shelf_days) < 0
          )
            throw new Error(
              "Complete the name, purchase date, shelf life and storage for each item.",
            );
          return {
            name: d.name,
            location: d.location,
            bought_date: d.bought_date,
            shelf_days: Number(d.shelf_days),
          };
        });
        await api("/items", post({ items }));
      } else {
        for (const d of drafts)
          if (!d.name.trim() || !d.category.trim() || !d.location.trim())
            throw new Error(
              "Complete the name, category and location for each household item.",
            );
        await api(
          "/household/batch",
          post({
            items: drafts.map((d) => ({
              name: d.name,
              category: d.category,
              location: d.location,
              ...(d.recorded_at
                ? { recorded_at: new Date(d.recorded_at).toISOString() }
                : {}),
            })),
          }),
        );
      }
      setDrafts([]);
      setTranscript("");
      setInfo("Items saved.");
      await refresh();
      setTab(kind === "food" ? "pantry" : "household");
    });
  const startMic = () =>
    run(async () => {
      if (liveRef.current)
        throw new Error("End the conversation before recording a note.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      let ctx: AudioContext | null = null;
      try {
        ctx = new AudioContext({ sampleRate: 24000 });
        if (ctx.sampleRate !== 24000)
          throw new Error(
            "This browser cannot record at 24 kHz. Try another browser or type your note.",
          );
        await ctx.audioWorklet.addModule("/pcm-worklet.js");
        const url = new URL("/api/voice/stream", location.href);
        url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(url);
        const node = new AudioWorkletNode(ctx, "pcm-worklet");
        const source = ctx.createMediaStreamSource(stream);
        const mute = ctx.createGain();
        mute.gain.value = 0;
        source.connect(node);
        node.connect(mute);
        mute.connect(ctx.destination);
        const current = { ws, stream, ctx, node } as NonNullable<
          typeof mic.current
        >;
        mic.current = current;
        node.port.onmessage = (e) => {
          if (e.data.type === "flushed") {
            current.flushed?.();
            return;
          }
          if (e.data.type === "audio" && ws.readyState === WebSocket.OPEN) {
            const bytes = new Uint8Array(e.data.buffer);
            let binary = "";
            for (const b of bytes) binary += String.fromCharCode(b);
            ws.send(JSON.stringify({ type: "audio", audio: btoa(binary) }));
          }
        };
        await new Promise<void>((resolve, reject) => {
          const timer = setTimeout(
            () => reject(new Error("Transcription connection timed out.")),
            20000,
          );
          ws.onerror = () => {
            clearTimeout(timer);
            reject(new Error("Could not connect to live transcription."));
          };
          ws.onmessage = (e) => {
            const event = JSON.parse(e.data);
            if (event.type === "ready") {
              clearTimeout(timer);
              setRecording(true);
              resolve();
            } else if (
              event.type === "conversation.item.input_audio_transcription.delta"
            ) {
              setTranscript((old) => old + event.delta);
            } else if (
              event.type ===
              "conversation.item.input_audio_transcription.completed"
            ) {
              setTranscript(event.transcript);
              setInfo("Transcript ready to review.");
              closeMic();
            } else if (
              event.type === "error" ||
              event.type.endsWith(".failed")
            ) {
              setError(event.error?.message || "Transcription failed.");
              closeMic();
            }
          };
          ws.onclose = () => {
            clearTimeout(timer);
            if (mic.current === current) {
              setRecording(false);
              setError("Transcription connection closed.");
              closeMic();
            }
          };
        });
      } catch (e) {
        stream.getTracks().forEach((t) => t.stop());
        if (ctx) await ctx.close();
        mic.current = null;
        throw e;
      }
    });
  const closeMic = () => {
    const m = mic.current;
    if (!m) return;
    mic.current = null;
    m.stream.getTracks().forEach((t) => t.stop());
    m.node.disconnect();
    m.ws.close();
    m.ctx.close().catch(() => {});
    setRecording(false);
  };
  const stopMic = () =>
    run(async () => {
      const m = mic.current;
      if (!m) return;
      setRecording(false);
      m.stream.getTracks().forEach((t) => t.stop());
      await new Promise<void>((resolve) => {
        m.flushed = resolve;
        m.node.port.postMessage("flush");
        setTimeout(resolve, 1000);
      });
      if (m.ws.readyState === WebSocket.OPEN) {
        m.ws.send(JSON.stringify({ type: "commit" }));
        setInfo("Finishing transcription…");
        setTimeout(() => {
          if (mic.current === m) {
            setError("Transcription timed out. Please retry.");
            closeMic();
          }
        }, 20000);
      } else closeMic();
    });
  const endLive = () => {
    const l = liveRef.current;
    if (!l) return;
    l.closed = true;
    if (l.fallbackTimer) clearTimeout(l.fallbackTimer);
    liveRef.current = null;
    l.stream.getTracks().forEach((t) => t.stop());
    l.audio.pause();
    setLive(false);
    try {
      if (l.dc.readyState === "open") {
        l.dc.send(JSON.stringify({ type: "session.close" }));
        setTimeout(() => l.pc.close(), 2000);
      } else l.pc.close();
    } catch {
      l.pc.close();
    }
  };
  const startLive = () =>
    run(async () => {
      if (mic.current)
        throw new Error("Finish recording before starting a conversation.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const pc = new RTCPeerConnection();
      const audio = new Audio();
      audio.autoplay = true;
      try {
        stream.getTracks().forEach((t) => pc.addTrack(t, stream));
        pc.ontrack = (e) => {
          audio.srcObject = e.streams[0];
          audio
            .play()
            .catch(() => setError("Tap the screen to allow audio playback."));
        };
        const dc = pc.createDataChannel("oai-events");
        const l = {
          pc,
          stream,
          dc,
          audio,
          history: "",
          userText: "",
          lastUserDelta: 0,
          fallbackTimer: null as ReturnType<typeof setTimeout> | null,
          lastSubmitted: "",
          pendingText: "",
          pendingTask: null as Promise<LiveResult> | null,
          delegationVersion: 0,
          closed: false,
        };
        liveRef.current = l;
        const applyResult = (result: LiveResult) => {
          if (
            (result.kind === "groceries" || result.kind === "household") &&
            result.items
          ) {
            setKind(result.kind === "groceries" ? "food" : "household");
            setDrafts(result.items.map(toDraft));
          }
          if (result.plan) setPlan(result.plan);
        };
        const requestTask = (text: string) => {
          if (l.pendingTask && l.pendingText === text) return l.pendingTask;
          const request = api<LiveResult>(
            "/live/delegate",
            post({ transcript: text }),
          );
          l.pendingText = text;
          l.pendingTask = request;
          request.then(
            () => {
              if (l.pendingTask === request) l.pendingTask = null;
            },
            () => {
              if (l.pendingTask === request) l.pendingTask = null;
            },
          );
          return request;
        };
        const queueFallback = () => {
          if (l.fallbackTimer) clearTimeout(l.fallbackTimer);
          l.fallbackTimer = setTimeout(async () => {
            if (
              l.closed ||
              !l.userText.trim() ||
              l.userText === l.lastSubmitted
            )
              return;
            const text = l.userText;
            const version = l.delegationVersion;
            l.lastSubmitted = text;
            try {
              const result = await requestTask(text);
              if (l.closed || version !== l.delegationVersion) return;
              applyResult(result);
              if (result.kind !== "clarify" && dc.readyState === "open")
                dc.send(
                  JSON.stringify({
                    type: "session.commentary.append",
                    delegation_id: null,
                    content: result.commentary,
                  }),
                );
            } catch {
              if (!l.closed)
                setError(
                  "Could not prepare the voice request. Review the transcript and try Extract items.",
                );
            }
          }, 1800);
        };
        dc.onmessage = async (e) => {
          const ev = JSON.parse(e.data);
          if (ev.type === "session.closed") {
            l.pc.close();
          }
          if (ev.type === "session.started") {
            setLive(true);
            setInfo(
              "Conversation connected. Ask about your pantry, meals or items.",
            );
          }
          if (ev.type === "session.input_transcript.delta") {
            l.userText = (l.userText + ev.delta).slice(-12000);
            l.lastUserDelta = Date.now();
            setTranscript(l.userText);
            queueFallback();
          }
          if (ev.type === "session.delegation.created") {
            l.delegationVersion++;
            if (l.fallbackTimer) clearTimeout(l.fallbackTimer);
            try {
              // Transcript fragments and delegation events arrive independently.
              const deadline = Date.now() + 2500;
              while (
                !l.closed &&
                Date.now() < deadline &&
                (!l.userText.trim() || Date.now() - l.lastUserDelta < 350)
              )
                await new Promise((resolve) => setTimeout(resolve, 100));
              if (!l.userText.trim())
                throw new Error("No user transcript was available.");
              const text = l.userText;
              l.lastSubmitted = text;
              const result = await requestTask(text);
              if (l.closed) return;
              applyResult(result);
              if (dc.readyState === "open")
                dc.send(
                  JSON.stringify({
                    type: "session.commentary.append",
                    delegation_id: ev.delegation.id,
                    content: result.commentary,
                  }),
                );
            } catch {
              if (dc.readyState === "open")
                dc.send(
                  JSON.stringify({
                    type: "session.commentary.append",
                    delegation_id: ev.delegation.id,
                    content:
                      "The request could not be completed. Nothing was saved.",
                  }),
                );
              setError("The voice request failed. Please retry.");
            }
          }
          if (ev.type === "error")
            setError("Live conversation reported an error.");
        };
        dc.onclose = () => {
          if (!l.closed) {
            endLive();
            setError("Conversation disconnected.");
          }
        };
        await pc.setLocalDescription(await pc.createOffer());
        if (pc.iceGatheringState !== "complete")
          await new Promise<void>((resolve) => {
            const timer = setTimeout(resolve, 5000);
            pc.onicegatheringstatechange = () => {
              if (pc.iceGatheringState === "complete") {
                clearTimeout(timer);
                resolve();
              }
            };
          });
        const result = await api<{ transport: { sdp: string } }>(
          "/live/session",
          post({ sdp: pc.localDescription?.sdp }),
        );
        await pc.setRemoteDescription({
          type: "answer",
          sdp: result.transport.sdp,
        });
      } catch (e) {
        endLive();
        stream.getTracks().forEach((t) => t.stop());
        pc.close();
        throw e;
      }
    });
  useEffect(
    () => () => {
      closeMic();
      endLive();
    },
    [],
  );
  const updateItem = () =>
    run(async () => {
      if (!editing) return;
      const d = editing.draft;
      if (
        !d.name.trim() ||
        !d.location.trim() ||
        (editing.kind === "food" &&
          (!d.bought_date ||
            d.shelf_days === "" ||
            !Number.isInteger(Number(d.shelf_days)) ||
            Number(d.shelf_days) < 0)) ||
        (editing.kind === "household" && !d.category.trim())
      )
        throw new Error("Complete all required item fields.");
      const body =
        editing.kind === "food"
          ? {
              name: d.name,
              location: d.location,
              bought_date: d.bought_date,
              shelf_days: Number(d.shelf_days),
            }
          : {
              name: d.name,
              category: d.category,
              location: d.location,
              ...(d.recorded_at
                ? { recorded_at: new Date(d.recorded_at).toISOString() }
                : {}),
            };
      await api(
        `/${editing.kind === "food" ? "items" : "household"}/${editing.id}`,
        { method: "PATCH", body: JSON.stringify(body) },
      );
      setEditing(null);
      await refresh();
      setInfo("Item updated.");
    });
  const setEdit = (key: keyof Draft, value: string) =>
    setEditing((e) => (e ? { ...e, draft: { ...e.draft, [key]: value } } : e));
  const draftFields = (
    d: Draft,
    onChange: (key: keyof Draft, value: string) => void,
    mode: "food" | "household",
  ) => (
    <div className="form-grid">
      <Field label="Name">
        <Input
          value={d.name}
          onChange={(e) => onChange("name", e.target.value)}
          placeholder="Item name"
        />
      </Field>
      {mode === "household" ? (
        <Field label="Category">
          <Input
            value={d.category}
            onChange={(e) => onChange("category", e.target.value)}
            placeholder="e.g. Electronics"
          />
        </Field>
      ) : (
        <Field label="Purchased">
          <Input
            type="date"
            value={d.bought_date}
            onChange={(e) => onChange("bought_date", e.target.value)}
          />
        </Field>
      )}
      <Field label="Location">
        {mode === "food" ? (
          <select
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
            value={d.location}
            onChange={(e) => onChange("location", e.target.value)}
          >
            <option value="">Choose a location</option>
            {["fridge", "freezer", "pantry", "other"].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        ) : (
          <Input
            value={d.location}
            onChange={(e) => onChange("location", e.target.value)}
            placeholder="e.g. Hallway drawer"
          />
        )}
      </Field>
      {mode === "food" && (
        <Field label="Expires on (if known)">
          <Input
            type="date"
            value={d.expiry_date_hint}
            onChange={(e) => onChange("expiry_date_hint", e.target.value)}
          />
        </Field>
      )}
      {mode === "food" ? (
        <Field label="Shelf life in days">
          <Input
            type="number"
            min="0"
            value={d.shelf_days}
            onChange={(e) => onChange("shelf_days", e.target.value)}
            placeholder="Required"
          />
        </Field>
      ) : (
        <Field label="Recorded time (optional)">
          <Input
            type="datetime-local"
            value={d.recorded_at ? d.recorded_at.slice(0, 16) : ""}
            onChange={(e) => onChange("recorded_at", e.target.value)}
          />
        </Field>
      )}
    </div>
  );
  const unread = alerts.filter((a) => a.channel === "app" && !a.is_read).length;
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="logo">
          save<b>x</b>
          <span
            style={{
              fontSize: 9,
              letterSpacing: 2,
              marginLeft: 8,
              color: "#71828a",
            }}
          >
            HOME
          </span>
        </div>
        <div className="eyebrow" style={{ padding: "0 13px 10px" }}>
          YOUR SPACE
        </div>
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`nav-btn ${tab === id ? "active" : ""}`}
            onClick={() => {
              setTab(id);
              setError("");
              setInfo("");
            }}
          >
            <Icon size={17} />
            {label}
            {id === "alerts" && unread > 0 && (
              <span style={{ marginLeft: "auto" }}>{unread}</span>
            )}
          </button>
        ))}
        <div className="nav-bottom">
          A little more order.
          <br />A lot less waste.
          <br />
          <a href="/profile" className="underline">
            Account settings
          </a>
        </div>
      </aside>
      <main className="content">
        <header className="top">
          <div className="eyebrow">YOUR HOME, SIMPLIFIED</div>
          <div className="top-actions">
            <a href="/profile">Account</a>
            <span>·</span>
            <a href="/login">Sign in</a>
          </div>
        </header>
        {error && (
          <div className="notice error" role="alert">
            {error}{" "}
            {signedOut && (
              <a href="/login" className="underline">
                Sign in
              </a>
            )}
          </div>
        )}
        {info && (
          <div className="notice" role="status">
            {info}
          </div>
        )}
        {tab === "pantry" && (
          <>
            <div className="page-head">
              <div>
                <div className="eyebrow">OVERVIEW / FOOD</div>
                <h1>Good to have you home.</h1>
                <p>Everything in your kitchen, right where you need it.</p>
              </div>
              <Button
                onClick={() => {
                  setKind("food");
                  setTab("voice");
                }}
              >
                <Plus size={15} /> Add item
              </Button>
            </div>
            <div className="stat-grid">
              <div className="stat">
                <div className="stat-label">In your pantry</div>
                <div className="stat-value">
                  {food.filter((i) => i.status === "active").length}
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Use soon</div>
                <div className="stat-value">
                  {
                    food.filter(
                      (i) => i.status === "active" && i.days_left <= 3,
                    ).length
                  }
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Household items</div>
                <div className="stat-value">{home.length}</div>
              </div>
            </div>
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2>Pantry inventory</h2>
                  <span>Sorted by expiry date</span>
                </div>
                <span>{food.length} items</span>
              </div>
              {food.length === 0 ? (
                <div className="empty">
                  Your pantry is clear. Add your first item to get started.
                </div>
              ) : (
                food.map((item) => (
                  <div className="item-row" key={item.id}>
                    <div className="item-main">
                      <div className="item-icon">
                        <Package size={18} />
                      </div>
                      <div>
                        <div className="item-name">{item.name}</div>
                        <div className="item-sub">
                          {item.location} · bought {item.bought_date} · expires{" "}
                          {item.expiry_date}
                        </div>
                      </div>
                    </div>
                    <div className="item-meta">
                      <span
                        className={`chip ${item.days_left <= 3 ? "urgent" : ""}`}
                      >
                        {item.status === "expired"
                          ? "Expired"
                          : item.days_left === 0
                            ? "Today"
                            : `${item.days_left} days left`}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setEditing({
                            kind: "food",
                            id: item.id,
                            draft: toDraft(item),
                          })
                        }
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Mark ${item.name} used`}
                        onClick={() =>
                          run(async () => {
                            await api(`/items/${item.id}`, {
                              method: "PATCH",
                              body: JSON.stringify({ status: "used" }),
                            });
                            await refresh();
                          })
                        }
                      >
                        <Check size={16} />
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </section>
          </>
        )}
        {tab === "household" && (
          <>
            <div className="page-head">
              <div>
                <div className="eyebrow">OVERVIEW / HOUSEHOLD</div>
                <h1>A place for everything.</h1>
                <p>
                  Remember what you have, where it is, and when you last noted
                  it.
                </p>
              </div>
              <Button
                onClick={() => {
                  setKind("household");
                  setTab("voice");
                }}
              >
                <Plus size={15} /> Add item
              </Button>
            </div>
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2>Household inventory</h2>
                  <span>Most recently recorded first</span>
                </div>
                <span>{home.length} items</span>
              </div>
              {home.length === 0 ? (
                <div className="empty">
                  No household items yet. Add the things you want to remember.
                </div>
              ) : (
                home.map((item) => (
                  <div className="item-row" key={item.id}>
                    <div className="item-main">
                      <div className="item-icon">
                        <Home size={18} />
                      </div>
                      <div>
                        <div className="item-name">{item.name}</div>
                        <div className="item-sub">
                          {item.category} · {item.location} ·{" "}
                          {localTime(item.recorded_at)}
                        </div>
                      </div>
                    </div>
                    <div className="item-meta">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setEditing({
                            kind: "household",
                            id: item.id,
                            draft: toDraft(item),
                          })
                        }
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Delete ${item.name}`}
                        onClick={() => {
                          if (window.confirm(`Delete ${item.name}?`))
                            run(async () => {
                              await api(`/household/${item.id}`, {
                                method: "DELETE",
                              });
                              await refresh();
                            });
                        }}
                      >
                        <Trash2 size={15} />
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </section>
          </>
        )}
        {tab === "voice" && (
          <>
            <div className="page-head">
              <div>
                <div className="eyebrow">ADD TO YOUR HOME</div>
                <h1>Say it. Save it.</h1>
                <p>
                  Speak or type the details, then review everything before
                  saving.
                </p>
              </div>
            </div>
            <div className="grid-two">
              <section className="panel">
                <div className="panel-head">
                  <div>
                    <h2>Describe your items</h2>
                    <span>Choose what you're adding</span>
                  </div>
                </div>
                <div className="panel-body">
                  <div className="flex gap-2 mb-4">
                    <Button
                      variant={kind === "food" ? "default" : "secondary"}
                      size="sm"
                      onClick={() => {
                        setKind("food");
                        setDrafts([]);
                      }}
                    >
                      Food
                    </Button>
                    <Button
                      variant={kind === "household" ? "default" : "secondary"}
                      size="sm"
                      onClick={() => {
                        setKind("household");
                        setDrafts([]);
                      }}
                    >
                      Household
                    </Button>
                  </div>
                  <Textarea
                    value={transcript}
                    onChange={(e) => setTranscript(e.target.value)}
                    rows={5}
                    placeholder={
                      kind === "food"
                        ? "Bought milk today, lasts five days, in the fridge."
                        : "My spare keys are in the hallway drawer."
                    }
                  />
                  <div className="btn-row">
                    <Button
                      variant={recording ? "destructive" : "secondary"}
                      disabled={busy}
                      onClick={recording ? stopMic : startMic}
                    >
                      {recording ? <MicOff size={15} /> : <Mic size={15} />}{" "}
                      {recording ? "Stop recording" : "Record voice note"}
                    </Button>
                    <Button disabled={busy} onClick={parse}>
                      <Sparkles size={15} />{" "}
                      {busy ? "Working…" : "Extract items"}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => setDrafts((d) => [...d, blank()])}
                    >
                      <Plus size={15} /> Add manually
                    </Button>
                  </div>
                  <div
                    style={{
                      borderTop: "1px solid #edf0f1",
                      marginTop: 24,
                      paddingTop: 20,
                    }}
                  >
                    <div className="item-name">Talk to SaveX</div>
                    <p className="item-sub">
                      Ask about your pantry or meals. Items are always reviewed
                      before saving.
                    </p>
                    <div className="btn-row">
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={live ? endLive : startLive}
                      >
                        <Radio size={15} />
                        {live ? "End conversation" : "Start conversation"}
                      </Button>
                    </div>
                  </div>
                </div>
              </section>
              <section className="panel">
                <div className="panel-head">
                  <div>
                    <h2>Review & confirm</h2>
                    <span>Nothing is saved until you confirm</span>
                  </div>
                  <span>{drafts.length} items</span>
                </div>
                <div className="panel-body">
                  {drafts.length === 0 ? (
                    <div className="empty">
                      Extract a description or add an item manually.
                    </div>
                  ) : (
                    drafts.map((d, i) => (
                      <div className="draft" key={i}>
                        <div className="flex justify-between items-center">
                          <h3>ITEM {String(i + 1).padStart(2, "0")}</h3>
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label="Remove item"
                            onClick={() =>
                              setDrafts((a) => a.filter((_, n) => n !== i))
                            }
                          >
                            <X size={15} />
                          </Button>
                        </div>
                        {d.quantity_text && (
                          <div className="item-sub">
                            Spoken quantity: {d.quantity_text}
                          </div>
                        )}
                        {d.clarification && (
                          <div className="notice">{d.clarification}</div>
                        )}
                        {draftFields(d, (k, v) => draftChange(i, k, v), kind)}
                      </div>
                    ))
                  )}
                  {drafts.length > 0 && (
                    <div className="btn-row">
                      <Button disabled={busy} onClick={save}>
                        <Check size={15} /> Confirm & save
                      </Button>
                    </div>
                  )}
                </div>
              </section>
            </div>
          </>
        )}
        {tab === "alerts" && (
          <>
            <div className="page-head">
              <div>
                <div className="eyebrow">YOUR REMINDERS</div>
                <h1>Nothing slips by.</h1>
                <p>Your expiry reminders and delivery history in one place.</p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api("/alerts/check", post({}));
                      await refresh();
                      setInfo("Expiry check completed.");
                    })
                  }
                >
                  Check now
                </Button>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api("/alerts/read", post({}));
                      await refresh();
                    })
                  }
                >
                  Mark read
                </Button>
              </div>
            </div>
            {notificationStatus && (
              <div className="notice">
                {notificationStatus.sms_enabled
                  ? notificationStatus.sms_number_configured
                    ? "SMS reminders are enabled."
                    : "Add a phone number in Account settings to receive SMS reminders."
                  : "SMS reminders are paused. In-app reminders and mocked calls still work."}{" "}
                Schedule timezone: {notificationStatus.timezone}.{" "}
                {!notificationStatus.sms_number_configured && (
                  <a href="/profile" className="underline">
                    Account settings
                  </a>
                )}
              </div>
            )}
            {notificationStatus &&
              notificationStatus.jobs.some(
                (job) => job.status === "pending" && job.channel !== "whatsapp",
              ) && (
                <section className="panel mb-4">
                  <div className="panel-head">
                    <div>
                      <h2>Upcoming reminders</h2>
                      <span>Times in {notificationStatus.timezone}</span>
                    </div>
                  </div>
                  {notificationStatus.jobs
                    .filter(
                      (job) =>
                        job.status === "pending" && job.channel !== "whatsapp",
                    )
                    .slice(0, 6)
                    .map((job) => (
                      <div className="item-row" key={job.id}>
                        <div>
                          <div className="item-name">
                            {job.items?.name || "Food item"}
                          </div>
                          <div className="item-sub">
                            {new Date(job.scheduled_at).toLocaleString(
                              undefined,
                              {
                                timeZone: notificationStatus.timezone,
                                dateStyle: "medium",
                                timeStyle: "short",
                              },
                            )}
                          </div>
                        </div>
                        <span className="chip">
                          {job.channel === "call_mock"
                            ? "Mock call"
                            : job.channel === "sms" &&
                                !notificationStatus.sms_enabled
                              ? "SMS paused"
                              : job.channel}
                        </span>
                      </div>
                    ))}
                </section>
              )}
            <section className="panel">
              <div className="panel-head">
                <h2>Recent activity</h2>
                <span>{unread} unread</span>
              </div>
              {alerts.length === 0 ? (
                <div className="empty">
                  No reminders yet. We'll keep an eye on your pantry.
                </div>
              ) : (
                alerts.map((a) => (
                  <div className="item-row" key={a.id}>
                    <div className="item-main">
                      <div className="item-icon">
                        <Bell size={17} />
                      </div>
                      <div>
                        <div className="item-name">{a.message}</div>
                        <div className="item-sub">
                          {a.channel} · {localTime(a.sent_at)} ·{" "}
                          {a.delivery_status}
                        </div>
                      </div>
                    </div>
                    <span className="chip">{a.level}</span>
                  </div>
                ))
              )}
            </section>
            <section className="panel mt-4">
              <div className="panel-head">
                <div>
                  <h2>Developer notification demo</h2>
                  <span>
                    Midnight start, accelerated · no SMS or calls are sent
                  </span>
                </div>
              </div>
              <div className="panel-body">
                <label htmlFor="demo-days" className="item-sub">
                  Simulate expiry window
                </label>
                <div className="flex gap-2 mt-2">
                  <select
                    id="demo-days"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                    value={demoDays}
                    onChange={(e) => setDemoDays(e.target.value)}
                  >
                    <option value="7">Seven days remaining</option>
                    <option value="3">Three days remaining</option>
                    <option value="0">Expires today</option>
                  </select>
                  <Button
                    disabled={busy || demoActive}
                    onClick={() =>
                      run(async () => {
                        setDemoActive(true);
                        setDemoEvents([]);
                        try {
                          const result = await api<{
                            events: {
                              channel: string;
                              scheduled_at: string;
                              message: string;
                            }[];
                          }>(
                            "/alerts/demo",
                            post({ days_remaining: Number(demoDays) }),
                          );
                          for (const event of result.events) {
                            await new Promise((resolve) =>
                              setTimeout(resolve, 500),
                            );
                            setDemoEvents((current) => [...current, event]);
                          }
                        } finally {
                          setDemoActive(false);
                        }
                      })
                    }
                  >
                    {demoActive ? "Running…" : "Run demo"}
                  </Button>
                </div>
                {demoEvents.length > 0 && (
                  <div className="mt-4" aria-live="polite">
                    {demoEvents.map((event, i) => (
                      <div className="item-row" key={i}>
                        <div>
                          <div className="item-name">{event.message}</div>
                          <div className="item-sub">
                            Scheduled for{" "}
                            {new Date(event.scheduled_at).toLocaleString(
                              undefined,
                              {
                                timeZone:
                                  notificationStatus?.timezone ||
                                  "Asia/Kolkata",
                                dateStyle: "medium",
                                timeStyle: "short",
                              },
                            )}{" "}
                            ({notificationStatus?.timezone || "Asia/Kolkata"})
                          </div>
                        </div>
                        <span className="chip">{event.channel}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
            <section className="panel mt-4">
              <div className="panel-head">
                <div>
                  <h2>Preview an expiry date</h2>
                  <span>Preview only · no changes or notifications</span>
                </div>
              </div>
              <div className="panel-body">
                <div className="flex gap-2">
                  <Input
                    type="date"
                    aria-label="Preview date"
                    value={previewDate}
                    onChange={(e) => setPreviewDate(e.target.value)}
                  />
                  <Button
                    variant="secondary"
                    disabled={busy || !previewDate}
                    onClick={() =>
                      run(async () => {
                        const result = await api<{ items: Food[] }>(
                          "/expiry/preview",
                          post({ as_of: previewDate }),
                        );
                        setPreview(result.items);
                      })
                    }
                  >
                    Preview
                  </Button>
                </div>
                {preview && (
                  <div className="mt-4">
                    {preview.length === 0 ? (
                      <p className="item-sub">No items to preview.</p>
                    ) : (
                      preview.map((item) => (
                        <div className="item-row" key={item.id}>
                          <span className="item-name">{item.name}</span>
                          <span className="chip">
                            {item.status === "expired"
                              ? "Expired"
                              : `${item.days_left} days left`}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            </section>
          </>
        )}
        {tab === "planner" && (
          <>
            <div className="page-head">
              <div>
                <div className="eyebrow">MAKE SOMETHING GOOD</div>
                <h1>What's cooking?</h1>
                <p>Three ideas built around what's already in your kitchen.</p>
              </div>
              <Button
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    setPlan(
                      await api<Plan>("/plan/research", post({ research })),
                    );
                  })
                }
              >
                <Sparkles size={15} /> {busy ? "Planning…" : "Plan my meals"}
              </Button>
            </div>
            <label className="flex gap-2 items-center mb-6 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={research}
                onChange={(e) => setResearch(e.target.checked)}
              />{" "}
              Find recipe inspiration and related photos with Exa
            </label>
            {plan?.notice && <div className="notice">{plan.notice}</div>}
            {!plan ? (
              <div className="panel empty">
                Your next three meals are just a click away.
              </div>
            ) : (
              <>
                <div className="planner-grid">
                  {(["breakfast", "lunch", "dinner"] as const).map((k) => (
                    <article className="panel meal" key={k}>
                      <div className="eyebrow">{k}</div>
                      {plan.meal_images?.[k] && (
                        <RecipePhoto
                          key={plan.meal_images[k]!.url}
                          image={plan.meal_images[k]!}
                          dish={plan.meals[k].dish}
                        />
                      )}
                      <h3>{plan.meals[k].dish}</h3>
                      <p>
                        <strong>Ingredients:</strong>{" "}
                        {plan.meals[k].items_used.join(", ")}
                      </p>
                      {plan.meals[k].priority_items.length > 0 && (
                        <span className="chip">
                          Use soon: {plan.meals[k].priority_items.join(", ")}
                        </span>
                      )}
                      <ol>
                        {plan.meals[k].steps.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ol>
                    </article>
                  ))}
                </div>
                {plan.meal_images &&
                  Object.keys(plan.meal_images).length > 0 &&
                  Object.values(plan.meal_images).every((image) => !image) && (
                    <div className="notice mt-4">
                      Related recipe photos are unavailable right now. Your meal
                      plan is ready.
                    </div>
                  )}
                {!!plan.sources?.length && (
                  <div className="panel panel-body sources mt-4">
                    <div className="eyebrow">RECIPE INSPIRATION</div>
                    {plan.sources.map((s) => (
                      <a
                        key={s.url}
                        href={s.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {s.title} ↗
                      </a>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        )}
        <Dialog
          open={!!editing}
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Edit item</DialogTitle>
              <DialogDescription>
                Update the details and save your changes.
              </DialogDescription>
            </DialogHeader>
            {editing && (
              <>
                {draftFields(editing.draft, setEdit, editing.kind)}
                <div className="btn-row">
                  <Button onClick={updateItem} disabled={busy}>
                    Save changes
                  </Button>
                  <Button variant="ghost" onClick={() => setEditing(null)}>
                    Cancel
                  </Button>
                </div>
              </>
            )}
          </DialogContent>
        </Dialog>
      </main>
      <nav className="mobile-nav" aria-label="Main navigation">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={tab === id ? "active" : ""}
            onClick={() => {
              setTab(id);
              setError("");
              setInfo("");
            }}
          >
            <Icon size={19} />
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}
