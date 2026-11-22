"""Posílání Rich Presence do Discordu (přes lokální spojení s aplikací Discord)."""

from __future__ import annotations

import logging

log = logging.getLogger("dbd")


class DiscordPresence:
    MIN_INTERVAL = 4.0   # s mezi aktualizacemi (Discord víc stejně nezobrazí)
    RETRY = 15.0         # s mezi pokusy o připojení

    def __init__(self, app_id: str, dry_run: bool = False) -> None:
        self.app_id = str(app_id).strip()
        self.dry_run = dry_run
        self.rpc = None
        self.desired: dict | None = None
        self.sent: dict | None | bool = False  # False = ještě nic neodesláno
        self.last_send = -1e9
        self.next_try = 0.0
        self._warned = False

    def set(self, activity: dict | None) -> None:
        self.desired = activity

    @property
    def connected(self) -> bool:
        return self.rpc is not None

    def _connect(self, now: float) -> bool:
        if self.rpc is not None:
            return True
        if now < self.next_try:
            return False
        from pypresence import Presence
        from pypresence.exceptions import DiscordNotFound, InvalidID

        try:
            rpc = Presence(self.app_id, connection_timeout=5, response_timeout=5)
            rpc.connect()
        except InvalidID:
            log.error("Discord odmítl Application ID '%s'. Zkontroluj ho v nastaveni.json.", self.app_id)
            self.next_try = now + 60
            return False
        except (DiscordNotFound, FileNotFoundError, ConnectionRefusedError):
            if not self._warned:
                log.warning("Discord neběží (nebo běží jen v prohlížeči). Zkouším to znovu každých %d s.",
                            int(self.RETRY))
                self._warned = True
            self.next_try = now + self.RETRY
            return False
        except Exception as e:
            log.warning("Nepodařilo se připojit k Discordu: %s", e)
            self.next_try = now + self.RETRY
            return False
        self.rpc = rpc
        self._warned = False
        log.info("Připojeno k Discordu.")
        return True

    def _drop(self) -> None:
        try:
            if self.rpc is not None:
                self.rpc.close()
        except Exception:
            pass
        self.rpc = None
        self.sent = False

    def tick(self, now: float) -> None:
        if self.desired == self.sent:
            return
        if self.desired is None and self.rpc is None and not self.dry_run:
            # Nic neukazujeme a nejsme připojení -> není co mazat (Discord
            # aktivitu odpojeného programu smaže sám). Nepřipojovat se zbytečně.
            self.sent = None
            return
        if now - self.last_send < self.MIN_INTERVAL:
            return
        if self.dry_run:
            log.info("[Discord] %s", self.desired if self.desired else "(nic)")
            self.sent, self.last_send = self.desired, now
            return
        if not self._connect(now):
            return
        try:
            if self.desired is None:
                self.rpc.clear()
            else:
                self.rpc.update(**self.desired)
            self.sent, self.last_send = self.desired, now
        except Exception as e:
            log.warning("Spojení s Discordem se přerušilo (%s). Připojím se znovu.", e.__class__.__name__)
            self._drop()
            self.next_try = now + 5

    def disconnect(self) -> None:
        """Odpojit se od Discordu (když hra neběží), aktivita zmizí."""
        if self.rpc is not None:
            self.close()
            self.sent = None
            self.desired = None
            log.debug("Odpojeno od Discordu (hra neběží).")

    def close(self) -> None:
        if self.rpc is not None:
            try:
                self.rpc.clear()
            except Exception:
                pass
        self._drop()
