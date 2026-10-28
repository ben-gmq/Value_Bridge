// Every UI string lives in en*.json, so a Japanese UI is a translation, not a refactor (§14.8).
// One file per screen area, so parallel work never edits the same file; keys are prefixed by
// area (processes.*, requirements.*, data.*, settings.*, solutions.*, frs.*, applications.*, interfaces.*, effort.*, components.*, baselines.*, home.*, codes.*, issues.*, waves.*, removals.*, grants.*, reports.*) and must not collide.
import en from './en.json';
import processes from './en.processes.json';
import requirements from './en.requirements.json';
import data from './en.data.json';
import settings from './en.settings.json';
import solutions from './en.solutions.json';
import frs from './en.frs.json';
import applications from './en.applications.json';
import interfaces from './en.interfaces.json';
import effortStrings from './en.effort.json';
import components from './en.components.json';
import baselines from './en.baselines.json';
import home from './en.home.json';
import codes from './en.codes.json';
import issues from './en.issues.json';
import waves from './en.waves.json';
import removals from './en.removals.json';
import grants from './en.grants.json';
import reports from './en.reports.json';

const ALL = { ...en, ...processes, ...requirements, ...data, ...settings, ...solutions, ...frs, ...applications, ...interfaces, ...effortStrings, ...components, ...baselines, ...home, ...codes, ...issues, ...waves, ...removals, ...grants, ...reports };

export function t(key, vars = {}) {
  const s = (vars.n === 1 && ALL[`${key}_one`]) || ALL[key] || key;      // "{n} fields" → "1 field"

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
