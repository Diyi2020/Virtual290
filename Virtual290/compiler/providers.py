"""
Virtual290 — provider abstraction.

Code asks for a ROLE ("compiler", "critic", "fast"); this module resolves it to
a configured provider. Swapping models is a YAML edit, never a code change.

Keys come from environment variables named in models.yaml. This module never
persists, logs, or forwards a key anywhere but the provider it belongs to.

    from providers import registry
    compiler = registry.get("compiler")
    board_script = compiler.complete(messages, schema=BIL_SCHEMA)

Install:  pip install pyyaml anthropic openai
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Protocol

import yaml

StructuredMode = Literal["native", "grammar", "prompt_only"]

# Which lab trained the model. Used to enforce that the critic is not the
# compiler wearing a hat.
#
# For hosted providers the endpoint identifies the lab. For open weights it does
# not — Qwen and Gemma both arrive over an OpenAI-compatible port but come from
# Alibaba and Google, and are genuinely independent reviewers of each other. So
# open-weight models are classified by model name, not by transport.
_HOSTED = {"anthropic": "anthropic", "openai": "openai", "google": "google"}

_OPEN_WEIGHTS = [
    ("qwen",    "alibaba"),
    ("gemma",   "google"),
    ("llama",   "meta"),
    ("mistral", "mistral"), ("mixtral", "mistral"),
    ("deepseek", "deepseek"),
    ("phi",     "microsoft"),
    ("olmo",    "ai2"),
    ("command", "cohere"),
]


def family_of(provider: str, model: str) -> str:
    """The lab that trained this model, for the critic-independence check."""
    if provider in _HOSTED:
        return _HOSTED[provider]
    m = model.lower()
    for prefix, lab in _OPEN_WEIGHTS:
        if prefix in m:
            return lab
    return f"unknown:{m}"      # unknown weights are their own family — never silently pass


# Kept for provider-level lookups that don't need model granularity.
FAMILY = dict(_HOSTED, ollama="open", openai_compatible="open")


@dataclass(frozen=True)
class Capabilities:
    context_window: int
    structured_output: StructuredMode
    tool_calling: bool
    reasoning_trace: bool
    native_audio: bool
    supports_caching: bool
    cost_per_mtok_in: float
    cost_per_mtok_out: float


@dataclass
class Response:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking: str | None = None

    def json(self) -> Any:
        """Parse as JSON, tolerating a ```json fence."""
        t = self.text.strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(t)


class ModelProvider(Protocol):
    name: str
    model: str
    family: str
    caps: Capabilities

    def complete(self, messages: list[dict], *, schema: dict | None = None,
                 tools: list | None = None, max_tokens: int = 8192) -> Response: ...

    def stream(self, messages: list[dict], **kw) -> Iterable[str]: ...


# --------------------------------------------------------------------------- #
# Implementations
# --------------------------------------------------------------------------- #

class AnthropicProvider:
    family = "anthropic"

    def __init__(self, model: str, api_key: str, *, thinking: bool = False, **kw):
        import anthropic
        self.name, self.model = "anthropic", model
        self._thinking = thinking
        self._c = anthropic.Anthropic(api_key=api_key)
        self.caps = Capabilities(200_000, "native", True, thinking, False, True, 15.0, 75.0)

    def complete(self, messages, *, schema=None, tools=None, max_tokens=8192) -> Response:
        kw: dict = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if self._thinking:
            kw["thinking"] = {"type": "enabled", "budget_tokens": max_tokens // 2}
        if schema:
            kw["tools"] = [{"name": "emit", "description": "Emit the result.",
                            "input_schema": schema}]
            kw["tool_choice"] = {"type": "tool", "name": "emit"}
        r = self._c.messages.create(**kw)
        think = next((b.thinking for b in r.content if b.type == "thinking"), None)
        if schema:
            blk = next(b for b in r.content if b.type == "tool_use")
            text = json.dumps(blk.input)
        else:
            text = "".join(b.text for b in r.content if b.type == "text")
        return Response(text, r.usage.input_tokens, r.usage.output_tokens, think)

    def stream(self, messages, **kw):
        with self._c.messages.stream(model=self.model, max_tokens=kw.get("max_tokens", 8192),
                                     messages=messages) as s:
            yield from s.text_stream


class OpenAIProvider:
    """OpenAI, and anything speaking its chat-completions protocol.

    `base_url` covers Together, Groq, Fireworks, vLLM, LM Studio, llama.cpp.
    NOTE: this is the OpenAI *API*, which a ChatGPT Pro subscription does not
    include. Create a key at platform.openai.com; it is billed separately.
    """
    def __init__(self, model: str, api_key: str | None, *, base_url: str | None = None,
                 family: str = "openai", structured_output: StructuredMode = "native", **kw):
        from openai import OpenAI
        self.name, self.model, self.family = "openai", model, family
        self._c = OpenAI(api_key=api_key or "not-needed", base_url=base_url)
        local = base_url is not None and "localhost" in base_url
        self.caps = Capabilities(
            128_000, structured_output, True, False, False, not local,
            0.0 if local else 1.25, 0.0 if local else 10.0)

    def complete(self, messages, *, schema=None, tools=None, max_tokens=8192) -> Response:
        kw: dict = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        if schema:
            if self.caps.structured_output == "native":
                kw["response_format"] = {"type": "json_schema",
                                         "json_schema": {"name": "out", "schema": schema,
                                                         "strict": True}}
            else:
                # Local servers: constrain decoding with a grammar compiled from
                # the schema (XGrammar in vLLM/SGLang, GBNF in llama.cpp). This is
                # what makes small models safe to put behind the compiler role.
                kw["extra_body"] = {"guided_json": schema}
        r = self._c.chat.completions.create(**kw)
        u = r.usage
        return Response(r.choices[0].message.content or "",
                        getattr(u, "prompt_tokens", 0), getattr(u, "completion_tokens", 0))

    def stream(self, messages, **kw):
        for ch in self._c.chat.completions.create(model=self.model, messages=messages,
                                                  stream=True, **kw):
            if ch.choices[0].delta.content:
                yield ch.choices[0].delta.content


class OllamaProvider:
    def __init__(self, model: str, *, base_url: str = "http://localhost:11434", **kw):
        self.name, self.model, self.family = "ollama", model, "open"
        self._url = base_url.rstrip("/")
        self.caps = Capabilities(32_000, "native", True, False, False, False, 0.0, 0.0)

    def complete(self, messages, *, schema=None, tools=None, max_tokens=8192) -> Response:
        import urllib.request
        body: dict = {"model": self.model, "messages": messages, "stream": False}
        if schema:
            body["format"] = schema          # Ollama takes a JSON Schema directly
        req = urllib.request.Request(
            f"{self._url}/api/chat", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            j = json.loads(r.read())
        return Response(j["message"]["content"],
                        j.get("prompt_eval_count", 0), j.get("eval_count", 0))

    def stream(self, messages, **kw):
        raise NotImplementedError("streaming not wired for Ollama yet")


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

class ConfigError(RuntimeError):
    pass


class Registry:
    def __init__(self, path: str | None = None):
        path = path or os.path.join(os.path.dirname(__file__), "models.yaml")
        with open(path) as f:
            self.cfg = yaml.safe_load(f)
        self.profile_name = os.environ.get("V290_PROFILE", self.cfg["active_profile"])
        try:
            self.profile = self.cfg["profiles"][self.profile_name]
        except KeyError:
            raise ConfigError(f"no such profile: {self.profile_name}")
        self._cache: dict[str, ModelProvider] = {}
        self._check_critic_independence()

    def _check_critic_independence(self) -> None:
        """A critic from the compiler's own family reviews its own blind spots."""
        rules = self.cfg.get("roles", {}).get("critic", {})
        other = rules.get("require_different_family_from")
        if not other or other not in self.profile or "critic" not in self.profile:
            return
        fam = lambda r: family_of(self.profile[r]["provider"], self.profile[r]["model"])
        if fam("critic") == fam(other):
            raise ConfigError(
                f"profile '{self.profile_name}': critic and {other} were both trained by "
                f"'{fam('critic')}'. Self-review reproduces the reviewer's own blind spots. "
                f"Point the critic at a model from a different lab."
            )

    def get(self, role: str) -> ModelProvider:
        if role in self._cache:
            return self._cache[role]
        try:
            spec = dict(self.profile[role])
        except KeyError:
            raise ConfigError(f"profile '{self.profile_name}' defines no role '{role}'")

        pname = spec.pop("provider")
        pcfg = self.cfg["providers"].get(pname, {})
        key = None
        if env := pcfg.get("api_key_env"):
            key = os.environ.get(env)
            if not key and not pcfg.get("api_key_optional"):
                raise ConfigError(
                    f"role '{role}' needs provider '{pname}', but ${env} is not set.\n"
                    f"  export {env}=...    (never commit it; nothing here stores it)"
                )
        spec.setdefault("base_url", pcfg.get("base_url"))

        if pname == "anthropic":
            p: ModelProvider = AnthropicProvider(api_key=key, **spec)
        elif pname in ("openai", "openai_compatible"):
            p = OpenAIProvider(api_key=key, family=FAMILY[pname], **spec)
        elif pname == "ollama":
            p = OllamaProvider(**{k: v for k, v in spec.items() if k != "base_url"}
                               | ({"base_url": spec["base_url"]} if spec.get("base_url") else {}))
        else:
            raise ConfigError(f"unknown provider '{pname}'")

        self._cache[role] = p
        return p

    def describe(self) -> str:
        out = [f"profile: {self.profile_name}"]
        for role, spec in self.profile.items():
            fam = FAMILY.get(spec["provider"], "?")
            out.append(f"  {role:<9} {spec['provider']:<18} {spec['model']:<28} [{fam}]")
        return "\n".join(out)


registry = Registry()

if __name__ == "__main__":
    print(registry.describe())
