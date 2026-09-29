// Browser-side rules for the data screens. The server is the authority for every one of them;
// these only let the screen say so before a round trip.
import { t } from '../../i18n/t';

// S1-6: field names are unique among live fields, normalised lower(btrim(name)).
export const normName = (s) => (s ?? '').trim().toLowerCase();

export const firstLine = (s) => (s ?? '').split(/\r?\n/)[0];

export const entityLabel = (e) => (e ? `${e.de_number} ${e.de_name}` : '');

// "12" for a length, "13,2" for precision and scale, "—" when nothing is set.
export function sizeText(f) {
  if (f.length_val != null) return String(f.length_val);
  if (f.precision_val != null) {
    return f.scale_val != null ? t('data.field.sizePs', { p: f.precision_val, s: f.scale_val }) : String(f.precision_val);
  }
  return t('data.none');
}

export const requiredText = (v) => t(v === true ? 'data.req.yes' : v === false ? 'data.req.no' : 'data.req.unknown');

// The two model checks Slice 1 shows, from the loaded fields only (the full report is later).
export function modelChecks(fields) {
  const out = [];
  const pk = fields.filter((f) => f.is_primary_key).sort((a, b) => (a.pk_ordinal ?? 0) - (b.pk_ordinal ?? 0));
  out.push(pk.length
    ? { tone: 'ok', text: t('data.check.pkSet', { names: pk.map((f) => f.field_name).join(', ') }) }
    : { tone: 'caution', text: t('data.check.noPk') });
  const fks = fields.filter((f) => f.is_foreign_key);
  const loose = fks.filter((f) => f.ref_data_field_id == null);
  if (loose.length) {
    out.push({ tone: 'caution', text: t('data.check.fkNoField', { names: loose.map((f) => f.field_name).join(', ') }) });
  } else if (fks.length) {
    out.push({ tone: 'ok', text: t('data.check.fkAllFields') });
  }
  return out;
}

// Relationship numbers other fields of this entity already use towards `targetId` (S1-7).
export function groupsTo(fields, targetId, exceptFieldId) {
  const s = new Set(fields.filter((f) => f.ref_data_entity_id === targetId && f.data_field_id !== exceptFieldId
    && f.fk_group_no != null).map((f) => f.fk_group_no));
  return [...s].sort((a, b) => a - b);
}

// Integer inputs: '' is "not set" (null); anything but plain digits is invalid (NaN), never
// truncated — the form blocks submit on NaN, so "1.5" or "12abc" is never sent as 1 or 12.
export const toInt = (v) => {
  const s = String(v ?? '').trim();
  if (s === '') return null;
  return /^\d+$/.test(s) ? Number(s) : Number.NaN;
};

// True when a typed integer is invalid: not digits, or outside [min, max].
export const intBad = (v, min, max = Number.MAX_SAFE_INTEGER) => {
  const n = toInt(v);
  return n !== null && !(Number.isSafeInteger(n) && n >= min && n <= max);
};

// The next free primary-key position: one past the highest used by the other key fields.
export const nextPkOrdinal = (fields, exceptFieldId) => Math.max(0, ...fields
  .filter((f) => f.is_primary_key && f.data_field_id !== exceptFieldId).map((f) => f.pk_ordinal ?? 0)) + 1;
