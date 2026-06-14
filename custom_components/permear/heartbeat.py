"""Heartbeat — the hourly attentional cycle, in-process (v8.9).

Replaces the shell chain cycles.yaml heartbeat automation +
build_heartbeat.py + memory_record_emit.py + aras_log_stats.py.

Flow (unchanged from production):
  build_candidates (event_buffer, 90-min window) → dedup by canonical key →
  dynamic threshold (MIN + maturity×(MAX−MIN)) → ARAS → emit direct /
  suppress / gray → ONE ai_task call for the gray zone (data provider,
  fallback choreography preserved) → emits recorded in Organic Memory with
  canonical key + score → ARAS stats accumulated.

What changed with the in-process port:
- states come from hass.states (no REST, no token);
- the gray-zone LLM runs via hass.services.async_call("ai_task", ...);
- direct-emission text is humanized from the event STATE for domains without
  rich metadata (switch/binary_sensor/lock/...) — fixes the "dry token" the
  shell chain could not resolve;
- scheduling via async_track_time_interval (hourly), window from permear.yaml,
  60–300s jitter preserved, single-run guard (= mode: single).

The Heartbeat is a physiological attentional cycle, not a proactivity loop.
Errors never become candidates from the buffer (filtered); the error monitor
stays external. All user-facing text is PT; code and logs are EN.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .aras import evaluate_salience
from .config import PermearConfig
from .const import (
    AGENT_CIRCUIT_RELATIVE_PATH,
    ARAS_MATURITY_FULL_RATIO,
    ARAS_MATURITY_MIN_ENTITIES,
    ARAS_STATS_RELATIVE_PATH,
    ARAS_SUPPRESS_THRESHOLD,
    ARCHIVED_ERRORS_RELATIVE_PATH,
    AVAILABILITY_RELATIVE_PATH,
    BATTERY_DEVICE_CLASSES,
    BATTERY_ENTITY_PATTERNS,
    BATTERY_THRESHOLD,
    FALLBACK_SKIP_PRIMARY_SECONDS,
    HEARTBEAT_INTERVAL_MINUTES,
    HEARTBEAT_JITTER_SECONDS,
    HEARTBEAT_WINDOW_MINUTES,
    MONITORED_ENTITIES_RELATIVE_PATH,
    SILENT_IGNORE_DOMAINS,
    SILENT_STATES,
)
from .notify import async_send_telegram, async_set_last_message
from .storage import PermearStorage, load_json, locked_json_update

_LOGGER = logging.getLogger(__name__)

GRAY_STRUCTURE = {
    "resposta": {
        "description": (
            "Alert messages to emit, or SILENCIO if nothing warrants attention."
        ),
        "required": True,
        "selector": {"text": {"multiline": True}},
    }
}

# Legacy curated trigger-id suffixes ("tv_sala_ligou") — kept for events
# recorded by the old shell capture during coexistence.
_HUMANIZE_VERBS = frozenset({
    "ligou", "desligou", "chegou", "saiu", "abriu", "fechou",
    "aberta", "fechada", "mudou", "ativo", "inativo",
})

# v8.9 — PT labels for raw HA states (v8.8 capture writes detalhe as
# "<object_id>_<state>"). User-facing text → PT. Closed, modest lists.
_GENERIC_STATE_PT = {
    "on": "ligado", "off": "desligado",
    "open": "aberto", "closed": "fechado",
}
_DOMAIN_STATE_PT = {
    "cover": {"open": "aberta", "closed": "fechada",
              "opening": "abrindo", "closing": "fechando"},
    "lock": {"locked": "trancada", "unlocked": "destrancada"},
    "climate": {"off": "desligado", "cool": "ligado em refrigeração",
                "heat": "ligado em aquecimento", "dry": "ligado em desumidificação",
                "fan_only": "ligado em ventilação", "auto": "ligado em modo automático",
                "heat_cool": "ligado em modo automático"},
    "media_player": {"playing": "reproduzindo", "paused": "pausado",
                     "idle": "ocioso", "on": "ligada", "off": "desligada"},
    "person": {"home": "chegou em casa", "not_home": "saiu de casa"},
    "device_tracker": {"home": "chegou em casa", "not_home": "saiu de casa"},
    "light": {"on": "acesa", "off": "apagada"},
}
_BINARY_SENSOR_DC_PT = {
    "door": ("aberta", "fechada"),
    "window": ("aberta", "fechada"),
    "opening": ("aberta", "fechada"),
    "garage_door": ("aberto", "fechado"),
    "motion": ("movimento detectado", "sem movimento"),
    "occupancy": ("presença detectada", "sem presença"),
    "presence": ("presença detectada", "sem presença"),
    "moisture": ("umidade detectada", "umidade normal"),
}


def _friendly(entity_id, states):
    state = states.get(entity_id)
    if state is None:
        return entity_id
    return state.attributes.get("friendly_name") or entity_id


def compute_dynamic_threshold(exposed_count, consolidated_count, t_min, t_max):
    """Emit threshold relative to memory maturity. Pure arithmetic — no LLM,
    never hand-tuned. maturity = consolidated/exposed, saturating at FULL_RATIO."""
    if not exposed_count or exposed_count < ARAS_MATURITY_MIN_ENTITIES:
        return t_min
    ratio = consolidated_count / exposed_count
    maturity = min(ratio / ARAS_MATURITY_FULL_RATIO, 1.0)
    return round(t_min + maturity * (t_max - t_min))


class PermearHeartbeat:
    """Schedules and runs the hourly attentional cycle."""

    def __init__(
        self, hass: HomeAssistant, storage: PermearStorage, config: PermearConfig
    ) -> None:
        self._hass = hass
        self._storage = storage
        self._config = config
        self._unsub = None
        self._task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    @callback
    def start(self) -> None:
        self._unsub = async_track_time_interval(
            self._hass,
            self._on_interval,
            timedelta(minutes=HEARTBEAT_INTERVAL_MINUTES),
        )
        _LOGGER.info(
            "Heartbeat scheduled every %d min, window %s–%s",
            HEARTBEAT_INTERVAL_MINUTES,
            self._config.heartbeat_start,
            self._config.heartbeat_end,
        )

    @callback
    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._task is not None:
            # Cancel an in-flight cycle (jitter sleep / LLM call) — an options
            # reload must not leave the old instance racing the new one.
            self._task.cancel()
            self._task = None

    def _in_window(self) -> bool:
        try:
            start = datetime.strptime(self._config.heartbeat_start, "%H:%M").time()
            end = datetime.strptime(self._config.heartbeat_end, "%H:%M").time()
        except ValueError:
            _LOGGER.warning(
                "Invalid heartbeat window %r–%r — skipping",
                self._config.heartbeat_start, self._config.heartbeat_end,
            )
            return False
        now_t = datetime.now().time()  # LOCAL time
        if start <= end:
            return start <= now_t < end
        return now_t >= start or now_t < end  # window crosses midnight

    async def _on_interval(self, _now) -> None:
        if self._running:  # mode: single
            _LOGGER.warning("Heartbeat still running — skipping this cycle")
            return
        if not self._in_window():
            return
        self._running = True
        self._task = asyncio.current_task()
        try:
            # Jitter preserved from cycles.yaml: avoid firing exactly on the hour
            await asyncio.sleep(random.randint(*HEARTBEAT_JITTER_SECONDS))
            await self.async_run()
        except Exception:  # noqa: BLE001 — the cycle must never crash HA
            _LOGGER.exception("Heartbeat cycle failed")
        finally:
            self._running = False
            self._task = None

    # ------------------------------------------------------------------
    # The cycle
    # ------------------------------------------------------------------

    async def async_run(self, health_summary: str = "HEALTH: OK") -> dict:
        """One full Heartbeat. Returns the stats dict (for tests/services)."""
        window_start = (
            datetime.now() - timedelta(minutes=HEARTBEAT_WINDOW_MINUTES)
        ).isoformat()  # LOCAL time
        db_ctx = await self._storage.async_heartbeat_context(window_start)
        monitored, circuit_health = await self._hass.async_add_executor_job(
            self._load_cycle_files
        )
        states = {s.entity_id: s for s in self._hass.states.async_all()}

        # File I/O (availability snapshot) lives inside — executor.
        candidates = await self._hass.async_add_executor_job(
            self._build_candidates,
            health_summary, monitored, states, db_ctx["events"], circuit_health,
        )
        user_state = self._build_user_state(monitored, db_ctx)

        emits, grays, suppressed = [], [], 0
        for cand in candidates:
            result = evaluate_salience(cand, user_state)
            if result["decision"] == "emit":
                emits.append((cand, result))
            elif result["decision"] == "gray":
                grays.append((cand, result))
            else:
                suppressed += 1

        for cand, result in emits:
            content = cand["content"]
            await self._deliver(content)
            await self._storage.async_record_emit(
                content, cand.get("key"),
                self._emit_metadata(cand.get("metadata"), result["salience"]),
            )

        llm_called = 0
        if grays:
            llm_called = 1
            prompt = self._build_gray_prompt(grays, states)
            resposta = await self._gray_zone_llm(prompt)
            if (
                resposta
                and "SILENCIO" not in resposta.upper()
                and len(resposta) > 2
            ):
                await self._deliver(resposta)
                await self._storage.async_record_interaction(
                    "heartbeat", resposta[:100]
                )
                # Gray-zone emission is keyless (LLM paraphrase — known limitation)
                await self._storage.async_record_emit(resposta, None, None)

        stats = {
            "total": len(candidates),
            "emit": len(emits),
            "gray": len(grays),
            "suppress": suppressed,
            "llm_calls": llm_called,
            "emit_threshold": user_state["emit_threshold"],
        }
        await self._hass.async_add_executor_job(self._log_stats, stats)
        _LOGGER.info(
            "Heartbeat: %(total)d candidates → %(emit)d emit, %(gray)d gray, "
            "%(suppress)d suppress (threshold %(emit_threshold)d)", stats,
        )
        return stats

    # ------------------------------------------------------------------
    # Candidate generation (executor — file I/O inside)
    # ------------------------------------------------------------------

    def _load_cycle_files(self) -> tuple:
        monitored = load_json(
            self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH),
            {"entities": []},
        )
        return monitored, self._circuit_health_summary()

    def _circuit_health_summary(self) -> str:
        """Read-only port of lib/agent.get_health_summary_for_prompt — same PT
        strings, but never resets/writes state (that stays with the shell)."""
        circuit = load_json(
            self._hass.config.path(AGENT_CIRCUIT_RELATIVE_PATH), {}
        )
        today = datetime.now().strftime("%Y-%m-%d")
        raw_stats = circuit.get("daily_stats") or {}
        stats = raw_stats if raw_stats.get("date") == today else {}

        archived = load_json(
            self._hass.config.path(ARCHIVED_ERRORS_RELATIVE_PATH), {"errors": {}}
        )
        archived_count = len(archived.get("errors", {}))

        open_until = None
        raw_open = circuit.get("circuit_open_until")
        if raw_open:
            try:
                open_until = datetime.fromisoformat(raw_open)
            except (ValueError, TypeError):
                open_until = None
        if open_until and datetime.now() < open_until:
            return (f"Saúde: circuit breaker aberto até "
                    f"{open_until.strftime('%H:%M')}, sistema degradado.")

        failures = stats.get("failures_3x", 0)
        retries_ok = stats.get("retries_recovered", 0)
        if failures >= 2:
            return f"Saúde: {failures} falhas finais hoje após retries — atenção."
        if archived_count >= 5:
            return f"Saúde: {archived_count} erros silenciados ativos."
        if retries_ok >= 2:
            return f"Saúde: agente recuperou de {retries_ok} hiccups hoje via retry."
        return ""

    def _build_candidates(
        self, health_summary, monitored, states, window_events, circuit_health
    ) -> list:
        candidates = []
        now_iso = datetime.now().isoformat()

        for ev in window_events:
            detalhe = ev.get("detalhe", "")
            if detalhe.startswith("erro:"):  # errors never go through ARAS
                continue
            entity_id = ev.get("entity_id")
            meta_str = ev.get("metadata", "{}")
            meta_dict = {}
            if meta_str and meta_str.strip() not in ("", "{}"):
                try:
                    meta_dict = json.loads(meta_str)
                except (json.JSONDecodeError, TypeError):
                    pass
            content = self._humanize_event(detalhe, entity_id, states)
            content = self._enrich_content(content, entity_id, meta_dict, states)
            candidates.append({
                "type": "event",
                "content": content,
                "entity_id": entity_id,
                "timestamp": ev.get("ts", now_iso),
                "metadata": meta_str,
            })

        if "SELF_ERRORS" in health_summary or "ERRORS" in health_summary:
            candidates.append({
                "type": "error", "content": health_summary,
                "entity_id": None, "timestamp": now_iso,
            })

        if circuit_health:
            candidates.append({
                "type": "health", "content": circuit_health,
                "entity_id": None, "timestamp": now_iso,
            })

        # Battery: all entities in the file (monitor=False incidental here)
        all_file_ids = {
            e.get("entity_id")
            for e in monitored.get("entities", [])
            if isinstance(e, dict) and e.get("entity_id")
        }
        candidates.extend(self._scan_battery_signals(states, all_file_ids))

        # Connectivity: global by design (events=exposed, health=global)
        candidates.extend(self._scan_silent_entities(states))

        seen: set = set()
        deduped = []
        for c in candidates:
            c["key"] = self._candidate_key(c)
            if c["key"] not in seen:
                seen.add(c["key"])
                deduped.append(c)
        return deduped

    @staticmethod
    def _candidate_key(cand) -> str:
        """Stable canonical key: type:entity_id, or type:content[:40]."""
        eid = cand.get("entity_id")
        ctype = cand.get("type", "event")
        if eid:
            return f"{ctype}:{eid}"
        content = (cand.get("content") or "").lower().strip()
        return f"{ctype}:{content[:40]}"

    def _humanize_event(self, detalhe, entity_id, states) -> str:
        """Raw detalhe → human PT text. v8.9: the in-process capture writes
        '<object_id>_<state>', so the state token itself is humanized — this
        gives switch/binary_sensor (no rich metadata) a real sentence."""
        if " " in detalhe:
            return detalhe  # already human-readable
        fname = ""
        if entity_id:
            state = states.get(entity_id)
            if state is not None:
                fname = state.attributes.get("friendly_name", "")

        if entity_id and "." in entity_id:
            object_id = entity_id.split(".", 1)[1]
            if detalhe.startswith(object_id + "_"):
                state_token = detalhe[len(object_id) + 1:]
                label = self._state_label_pt(entity_id, state_token, states)
                name = fname or object_id.replace("_", " ")
                if label:
                    return f"{name}: {label}"
                return f"{name}: {state_token}"

        # Legacy curated trigger ids ("tv_sala_ligou") — shell coexistence
        suffix = detalhe.rsplit("_", 1)[-1]
        if fname:
            if suffix in _HUMANIZE_VERBS:
                return f"{fname}: {suffix}"
            return fname
        return detalhe.replace("_", " ").capitalize()

    @staticmethod
    def _state_label_pt(entity_id, state_token, states) -> str | None:
        domain = entity_id.split(".", 1)[0]
        if domain == "binary_sensor":
            dc = ""
            state = states.get(entity_id)
            if state is not None:
                dc = state.attributes.get("device_class", "") or ""
            on_label, off_label = _BINARY_SENSOR_DC_PT.get(
                dc, ("ativado", "desativado")
            )
            if state_token == "on":
                return on_label
            if state_token == "off":
                return off_label
            return None
        label = _DOMAIN_STATE_PT.get(domain, {}).get(state_token)
        if label:
            return label
        return _GENERIC_STATE_PT.get(state_token)

    @staticmethod
    def _enrich_content(content, entity_id, meta, states) -> str:
        """Rich direct-emission text from per-type metadata (v8.4 contract)."""
        if not meta or not entity_id:
            return content
        domain = entity_id.split(".")[0]
        fname = _friendly(entity_id, states)

        if domain == "cover" and "position" in meta:
            try:
                pos = int(meta["position"])
                return f"{fname}: fechada" if pos == 0 else f"{fname}: aberta a {pos}%"
            except (ValueError, TypeError):
                pass
        elif domain == "media_player" and meta.get("title"):
            return f"{fname}: tocando '{meta['title']}'"
        elif domain == "light" and "brightness" in meta:
            try:
                # brightness is 0–255 in HA — convert to percent (shell showed raw)
                pct = round(int(meta["brightness"]) * 100 / 255)
                return f"{fname}: ligada a {pct}%"
            except (ValueError, TypeError):
                pass
        elif domain == "climate":
            temp = meta.get("temp")
            setpoint = meta.get("setpoint")
            if temp is not None and setpoint is not None:
                try:
                    return (f"{fname}: {float(temp):.0f}°C "
                            f"(setpoint {float(setpoint):.0f}°C)")
                except (ValueError, TypeError):
                    pass
            elif temp is not None:
                try:
                    return f"{fname}: {float(temp):.0f}°C"
                except (ValueError, TypeError):
                    pass
        return content

    def _scan_battery_signals(self, states, monitored_ids) -> list:
        candidates = []
        now_iso = datetime.now().isoformat()
        for eid, state in states.items():
            if eid not in monitored_ids:
                continue
            dc = state.attributes.get("device_class", "") or ""
            is_battery = (dc in BATTERY_DEVICE_CLASSES
                          or any(p in eid for p in BATTERY_ENTITY_PATTERNS))
            if not is_battery:
                continue
            try:
                level = float(state.state)
            except (ValueError, TypeError):
                continue
            if level < BATTERY_THRESHOLD:
                friendly = state.attributes.get("friendly_name", eid)
                candidates.append({
                    "type": "battery_low",
                    "content": f"Bateria baixa: {friendly} em {level:.0f}%",
                    "entity_id": eid,
                    "timestamp": now_iso,
                })
        return candidates

    def _scan_silent_entities(self, states) -> list:
        """Available → silent transitions. Global by design. flock-shared with
        the shell heartbeat during coexistence (same snapshot file)."""
        now_iso = datetime.now().isoformat()
        candidates = []
        path = self._hass.config.path(AVAILABILITY_RELATIVE_PATH)

        with locked_json_update(path, {}) as snapshot:
            new_snapshot = {}
            for eid, state in states.items():
                domain = eid.split(".")[0]
                if domain in SILENT_IGNORE_DOMAINS:
                    continue
                is_silent = state.state in SILENT_STATES
                cur_label = "silent" if is_silent else "available"
                new_snapshot[eid] = {"last_state": cur_label, "since": now_iso}

                prev = snapshot.get(eid)
                if prev:
                    if prev.get("last_state") == cur_label:
                        new_snapshot[eid]["since"] = prev.get("since", now_iso)
                    if prev.get("last_state") == "available" and is_silent:
                        friendly = state.attributes.get("friendly_name", eid)
                        candidates.append({
                            "type": "entity_silent",
                            "content": f"Dispositivo parou de responder: {friendly}",
                            "entity_id": eid,
                            "timestamp": now_iso,
                        })
            snapshot.clear()
            snapshot.update(new_snapshot)
        return candidates

    # ------------------------------------------------------------------
    # User state / ARAS context
    # ------------------------------------------------------------------

    def _build_user_state(self, monitored, db_ctx) -> dict:
        priorities = {}
        exposed = []
        for e in monitored.get("entities", []):
            if not e.get("monitor", True):
                continue
            eid = e.get("entity_id")
            if eid:
                priorities[eid] = int(e.get("priority", 0))
                exposed.append(eid)

        emit_threshold = compute_dynamic_threshold(
            len(exposed), db_ctx["consolidated_count"],
            self._config.threshold_min, self._config.threshold_max,
        )
        return {
            # v9.0.2: restrictions are LEARNED memories (kind='behavior_rule',
            # extracted from natural conversation by Sleep) — they lower the
            # score via _user_match, never silence absolutely, and decay
            # organically with the tiers
            "restrictions": db_ctx.get("restrictions", []),
            "recent_alerts": db_ctx["recent_keys"],
            "entity_priorities": priorities,
            "current_hour": datetime.now().hour,
            "emit_threshold": emit_threshold,
            "suppress_threshold": ARAS_SUPPRESS_THRESHOLD,
        }

    @staticmethod
    def _emit_metadata(raw_meta, score) -> dict:
        """Merge the ARAS score into the event metadata for the emit record."""
        if isinstance(raw_meta, dict):
            meta = dict(raw_meta)
        elif raw_meta:
            try:
                meta = json.loads(raw_meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        else:
            meta = {}
        meta["score"] = score
        return meta

    # ------------------------------------------------------------------
    # Gray zone — ONE ai_task call (data provider), fallback preserved
    # ------------------------------------------------------------------

    def _build_gray_prompt(self, grays, states) -> str:
        """PT prompt ending with the SILENCIO sentinel. Do not translate."""
        itens_parts = []
        for c, r in grays:
            line = f"  - {c['content']} (saliencia {r['salience']})"
            eid = c.get("entity_id")
            state = states.get(eid) if eid else None
            if state is not None:
                attrs = state.attributes
                dc = attrs.get("device_class", "") or eid.split(".")[0]
                unit = attrs.get("unit_of_measurement", "")
                state_str = f"{state.state}{' ' + unit if unit else ''}"
                last_upd = state.last_updated.astimezone().strftime("%Y-%m-%d %H:%M")
                line += (f"\n  [estado atual: {state_str} | tipo: {dc}"
                         f" | última atualização: {last_upd}]")
            itens_parts.append(line)
        itens = "\n".join(itens_parts)

        return f"""Avalie quais destes eventos merecem avisar o morador AGORA.

EVENTOS A AVALIAR (zona cinzenta do filtro de saliencia):
{itens}

Para CADA evento, decida emitir ou silenciar. Responda so com os eventos que
merecem aviso, em mensagens curtas (max 2 frases cada). Se nenhum merece,
responda EXATAMENTE: SILENCIO."""

    async def _gray_zone_llm(self, prompt: str) -> str | None:
        """Choreography from cycles.yaml: skip primary if a fallback was logged
        in the last hour; otherwise primary → fallback on empty response."""
        if not self._config.data and not self._config.data_fallback:
            _LOGGER.error("No data provider configured in permear.yaml — "
                          "gray zone skipped")
            return None

        recent_fb = await self._hass.async_add_executor_job(self._recent_fallback)

        if recent_fb and self._config.data_fallback:
            await self._hass.async_add_executor_job(self._log_fallback)
            return await self._call_ai_task(
                self._config.data_fallback, "ARAS gray zone [skip-primary]", prompt
            )

        resposta = None
        if self._config.data:
            resposta = await self._call_ai_task(
                self._config.data, "ARAS gray zone", prompt
            )
        if not resposta and self._config.data_fallback:
            await self._hass.async_add_executor_job(self._log_fallback)
            resposta = await self._call_ai_task(
                self._config.data_fallback, "ARAS gray zone [fallback]", prompt
            )
        return resposta

    async def _call_ai_task(
        self, entity_id: str, task_name: str, prompt: str
    ) -> str | None:
        try:
            resp = await self._hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "task_name": task_name,
                    "entity_id": entity_id,
                    "instructions": prompt,
                    "structure": GRAY_STRUCTURE,
                },
                blocking=True,
                return_response=True,
            )
        except Exception as exc:  # noqa: BLE001 — 429/Timeout still propagate
            _LOGGER.warning("ai_task %s via %s failed: %s", task_name, entity_id, exc)
            return None
        data = (resp or {}).get("data") or {}
        resposta = str(data.get("resposta") or "").strip()
        return resposta or None

    def _recent_fallback(self) -> bool:
        circuit = load_json(
            self._hass.config.path(AGENT_CIRCUIT_RELATIVE_PATH), {}
        )
        raw = circuit.get("last_fallback_at")
        if not raw:
            return False
        try:
            last_fb = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return False
        delta = (datetime.now() - last_fb).total_seconds()
        return 0 <= delta < FALLBACK_SKIP_PRIMARY_SECONDS

    def _log_fallback(self) -> None:
        """Port of log_fallback.py — same agent_circuit.json shape, flock-shared
        with the shell during coexistence."""
        today = datetime.now().strftime("%Y-%m-%d")
        path = self._hass.config.path(AGENT_CIRCUIT_RELATIVE_PATH)
        with locked_json_update(path, {}) as circuit:
            stats = circuit.get("daily_stats") or {}
            if stats.get("date") != today:
                stats = {"date": today, "errors_503_seen": 0,
                         "retries_recovered": 0, "failures_3x": 0,
                         "circuit_opens": 0, "fallbacks": 0}
            stats["fallbacks"] = stats.get("fallbacks", 0) + 1
            circuit["daily_stats"] = stats
            circuit["last_fallback_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

    # ------------------------------------------------------------------
    # Delivery + stats
    # ------------------------------------------------------------------

    async def _deliver(self, message: str) -> None:
        """Telegram (PT, chat_id from the config entry) + last-message holder.
        Best-effort each (notify.py logs failures, never raises)."""
        await async_send_telegram(self._hass, message)
        await async_set_last_message(self._hass, message)

    def _log_stats(self, stats: dict) -> None:
        """Accumulate the day's ARAS stats (ports aras_log_stats.py) —
        flock-shared file, same format the shell sensor reads."""
        today = datetime.now().strftime("%Y-%m-%d")
        path = self._hass.config.path(ARAS_STATS_RELATIVE_PATH)
        with locked_json_update(path, {}) as s:
            if s.get("data") != today:
                s.clear()
                s.update({"data": today, "total": 0, "emit": 0,
                          "gray": 0, "suppress": 0, "llm_calls": 0})
            # .get(k, 0): the file is external/editable — a missing key must
            # not abort the end of a cycle whose emissions already went out
            for k in ("total", "emit", "gray", "suppress", "llm_calls"):
                s[k] = s.get(k, 0) + stats[k]
            s["emit_threshold"] = stats["emit_threshold"]  # last seen, not summed
