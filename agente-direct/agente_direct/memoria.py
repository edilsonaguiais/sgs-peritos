"""Histórico das conversas e ficha BANT de cada lead, em SQLite."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa TEXT NOT NULL,
    papel TEXT NOT NULL,            -- 'user' (lead), 'assistant' (agente), 'humano' (você)
    texto TEXT NOT NULL,
    mid TEXT UNIQUE,
    criado_em REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mensagens_conversa ON mensagens(conversa, id);

CREATE TABLE IF NOT EXISTS leads (
    conversa TEXT PRIMARY KEY,
    username TEXT,
    nome TEXT,
    ficha TEXT,                     -- JSON com BANT, produto, estágio, resumo
    pausado_ate REAL DEFAULT 0,
    transferido INTEGER DEFAULT 0,
    atualizado_em REAL
);

CREATE TABLE IF NOT EXISTS enviados (
    mid TEXT PRIMARY KEY            -- mids que o próprio agente enviou (para separar dos ecos humanos)
);
"""


class Memoria:
    def __init__(self, caminho: Path | str):
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(caminho), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._trava = threading.Lock()
        with self._trava:
            self._db.executescript(ESQUEMA)

    # --- mensagens -------------------------------------------------------
    def registrar(self, conversa: str, papel: str, texto: str, mid: str | None = None) -> bool:
        """Grava a mensagem. Devolve False se o mid já existia (webhook repetido)."""
        with self._trava:
            try:
                self._db.execute(
                    "INSERT INTO mensagens (conversa, papel, texto, mid, criado_em) VALUES (?,?,?,?,?)",
                    (conversa, papel, texto, mid, time.time()),
                )
                self._db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def ja_vista(self, mid: str) -> bool:
        with self._trava:
            linha = self._db.execute("SELECT 1 FROM mensagens WHERE mid = ?", (mid,)).fetchone()
        return linha is not None

    def historico(self, conversa: str, limite: int = 60) -> list[dict]:
        """Histórico no formato da API de mensagens (papéis user/assistant alternados)."""
        with self._trava:
            linhas = self._db.execute(
                "SELECT papel, texto FROM mensagens WHERE conversa = ? ORDER BY id DESC LIMIT ?",
                (conversa, limite),
            ).fetchall()
        mensagens: list[dict] = []
        for linha in reversed(linhas):
            papel, texto = linha["papel"], linha["texto"]
            if papel == "humano":
                # Resposta que você mandou à mão: o agente vê como fala do lado da empresa.
                papel, texto = "assistant", f"[resposta enviada manualmente pela equipe] {texto}"
            if mensagens and mensagens[-1]["role"] == papel:
                mensagens[-1]["content"] += "\n" + texto
            else:
                mensagens.append({"role": papel, "content": texto})
        while mensagens and mensagens[0]["role"] != "user":
            mensagens.pop(0)
        return mensagens

    # --- mids enviados pelo agente --------------------------------------
    def marcar_enviado(self, mid: str) -> None:
        with self._trava:
            self._db.execute("INSERT OR IGNORE INTO enviados (mid) VALUES (?)", (mid,))
            self._db.commit()

    def foi_enviado_pelo_agente(self, mid: str) -> bool:
        with self._trava:
            return self._db.execute("SELECT 1 FROM enviados WHERE mid = ?", (mid,)).fetchone() is not None

    # --- leads -----------------------------------------------------------
    def lead(self, conversa: str) -> dict:
        with self._trava:
            linha = self._db.execute("SELECT * FROM leads WHERE conversa = ?", (conversa,)).fetchone()
        if not linha:
            return {"conversa": conversa, "username": None, "nome": None, "ficha": None,
                    "pausado_ate": 0.0, "transferido": 0}
        dados = dict(linha)
        dados["ficha"] = json.loads(dados["ficha"]) if dados["ficha"] else None
        return dados

    def atualizar_lead(self, conversa: str, **campos) -> None:
        if "ficha" in campos and campos["ficha"] is not None:
            campos["ficha"] = json.dumps(campos["ficha"], ensure_ascii=False)
        campos["atualizado_em"] = time.time()
        with self._trava:
            self._db.execute("INSERT OR IGNORE INTO leads (conversa) VALUES (?)", (conversa,))
            sets = ", ".join(f"{k} = ?" for k in campos)
            self._db.execute(f"UPDATE leads SET {sets} WHERE conversa = ?", (*campos.values(), conversa))
            self._db.commit()

    def pausar(self, conversa: str, horas: float) -> None:
        self.atualizar_lead(conversa, pausado_ate=time.time() + horas * 3600)

    def esta_pausado(self, conversa: str) -> bool:
        lead = self.lead(conversa)
        return bool(lead["transferido"]) or lead["pausado_ate"] > time.time()

    def listar_leads(self) -> list[dict]:
        with self._trava:
            conversas = [r["conversa"] for r in self._db.execute(
                "SELECT conversa FROM leads ORDER BY atualizado_em DESC")]
        return [self.lead(c) for c in conversas]
