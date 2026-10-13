import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Accordion, AccordionDetails, AccordionSummary, Box, Typography } from '@mui/material';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import { bfcApi, brApi, frApi, partyApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useAuth } from '../../app/AuthContext';
import { t } from '../../i18n/t';

// The panel's tertiary sections (D-63): collapsed, with a count and a one-line summary. Which are open is
// remembered per user in this browser — a convenience only, so every read and write tolerates blocked storage.
const storeKey = (userId) => `vb.processPanel.open.${userId ?? 'anon'}`;

// D-66 (slice 13a): Solutions and Function requirements open on a first visit (nothing stored yet); from then on
// the user's own choice is kept. A choice stored before the split named one "delivery" section: it carries over.
const OPEN_FIRST = ['solutions', 'frs'];

function readOpen(userId) {
  try {
    const raw = window.localStorage.getItem(storeKey(userId));
    if (raw == null) return OPEN_FIRST;
    const v = JSON.parse(raw);
    if (!Array.isArray(v)) return OPEN_FIRST;
    return v.includes('delivery') ? [...v.filter((k) => k !== 'delivery'), ...OPEN_FIRST] : v;
  } catch {
    return OPEN_FIRST;
  }
}

export function useOpenSections() {
  const { me } = useAuth() ?? {};
  const userId = me?.user?.app_user_id ?? me?.user?.email;
  const [open, setOpen] = useState(() => readOpen(userId));
  const toggle = useCallback((key) => setOpen((prev) => {
    const next = prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key];
    try { window.localStorage.setItem(storeKey(userId), JSON.stringify(next)); } catch { /* storage blocked: keep it in memory */ }
    return next;
  }), [userId]);
  return { isOpen: (key) => open.includes(key), toggle };
}

/** One collapsed section. Content stays mounted while collapsed (MUI's default), so closing never drops a draft. */
export function PanelSection({ id, title, count, summary, sections, children }) {
  const expanded = sections.isOpen(id);
  return (
    <Accordion disableGutters elevation={0} expanded={expanded} onChange={() => sections.toggle(id)}
      sx={(th) => ({ bgcolor: 'transparent', borderTop: `1px solid ${th.vars.palette.divider}`, borderRadius: 0,
        '&::before': { display: 'none' } })}>
      <AccordionSummary expandIcon={<ExpandMoreRounded />} aria-controls={`sec-${id}-body`} id={`sec-${id}-head`}
        sx={{ px: 0, minHeight: 52, '& .MuiAccordionSummary-content': { my: 1, minWidth: 0, alignItems: 'baseline', gap: 1 } }}>
        <Typography component="h3" sx={{ fontSize: 14, fontWeight: 600, flex: 'none' }}>{title}</Typography>
        {count != null && (
          <Box component="span" sx={(th) => ({ fontSize: 12.5, fontWeight: 600, color: th.vars.palette.brand.muted, flex: 'none' })}>
            {count}</Box>)}
        {summary && !expanded && (
          <Box component="span" sx={(th) => ({ fontSize: 12.5, color: th.vars.palette.brand.muted, minWidth: 0,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' })}>{summary}</Box>)}
      </AccordionSummary>
      <AccordionDetails id={`sec-${id}-body`} sx={{ px: 0, pt: 0, pb: 2, display: 'flex', flexDirection: 'column', gap: 2.5 }}>
        {children}
      </AccordionDetails>
    </Accordion>
  );
}

const firstLine = (s) => (s ?? '').split('\n').find((l) => l.trim())?.trim() ?? '';
const listSummary = (names) => (names.length ? names.join(' · ') : t('processes.sec.none'));

/** The counts and summaries, from the same queries (and caches) as the editors inside. */
export function useSectionFacts({ projectId, br, nodeId, solutionsOn, frsOn, partiesOn, systemsOn }) {
  const brId = br?.br_id;
  const solsQ = useQuery({ queryKey: [...keys.solutionLinks(), 'br', String(brId)], queryFn: () => brApi.solutions(brId),
    enabled: Boolean(brId) && solutionsOn });
  const frsQ = useQuery({ queryKey: keys.brFrs(brId), queryFn: () => frApi.ofBr(brId), enabled: Boolean(brId) && frsOn });
  const flowsQ = useQuery({ queryKey: [...keys.node(nodeId), 'flows'], queryFn: () => bfcApi.flows(nodeId),
    enabled: partiesOn });
  const partiesQ = useQuery({ queryKey: keys.parties(projectId), queryFn: () => partyApi.list(projectId),
    enabled: partiesOn });
  const appsQ = useQuery({ queryKey: keys.appLinksOf('step', nodeId), queryFn: () => bfcApi.apps(nodeId),
    enabled: systemsOn });
  const sols = solsQ.data ?? [];
  const frs = frsQ.data ?? [];
  return {
    // D-66: numbers and names, as the sections' own lists show them
    solutions: { count: sols.length, summary: listSummary(sols.map((s) => `${s.solution_number} ${s.solution_name}`)) },
    frs: { count: frs.length, summary: listSummary(frs.map((f) => `${f.fr_number} ${f.fr_name}`)) },
    parties: { count: (flowsQ.data ?? []).length, summary: listSummary([...new Set((flowsQ.data ?? []).map((f) => (partiesQ.data ?? [])
      .find((p) => p.external_entity_id === f.external_entity_id)?.ext_name).filter(Boolean))]) },
    systems: { count: (appsQ.data ?? []).length, summary: listSummary((appsQ.data ?? []).map((a) => a.application_name)) },
    description: (purpose) => firstLine(purpose) || t('processes.sec.descriptionEmpty'),
  };
}
