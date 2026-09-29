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
