// Every UI string lives in en.json, so a Japanese UI is a translation, not a refactor (§14.8).
import en from './en.json';

export function t(key, vars = {}) {
  const s = en[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''));
}
