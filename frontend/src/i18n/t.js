// Every UI string lives in en*.json, so a Japanese UI is a translation, not a refactor (§14.8).
// One file per screen area, so parallel work never edits the same file; keys are prefixed by
// area (processes.*, requirements.*, data.*, settings.*) and must not collide.
import en from './en.json';
import processes from './en.processes.json';
import requirements from './en.requirements.json';
import data from './en.data.json';
import settings from './en.settings.json';

const ALL = { ...en, ...processes, ...requirements, ...data, ...settings };

export function t(key, vars = {}) {
  const s = ALL[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''));
}

// A message the server also sent in English (e.g. an import Msg): the translation only when it
// exists and every {name} it uses is in vars, otherwise the server's own text.
export function tOr(key, vars, fallback) {
  const s = ALL[key];
  if (s === undefined) return fallback;
  const names = [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);
  return names.every((k) => Object.hasOwn(vars, k)) ? t(key, vars) : fallback;
}
