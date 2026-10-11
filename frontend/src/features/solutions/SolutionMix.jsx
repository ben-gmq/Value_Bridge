import { useQuery } from '@tanstack/react-query';
import { Box, Typography } from '@mui/material';
import { solutionApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { MONO } from '../../theme/theme';

/**
 * The project's solution mix by category (mockup 05's side panel), counted from the live register.
 * The mockup also splits by business area; solutions carry no area today, so that axis is left out (D-51).
 */
export function SolutionMix({ projectId, current }) {
  const q = useQuery({ queryKey: keys.solutions(projectId), queryFn: () => solutionApi.list(projectId) });
  const { codes } = useCodes(projectId, 'SOLUTION_CATEGORY');
  const live = (q.data ?? []).filter((s) => s.is_active);
  const counts = new Map();
  for (const s of live) counts.set(s.category_code, (counts.get(s.category_code) ?? 0) + 1);
  const max = Math.max(1, ...counts.values());

  return (
    <Card title={t('solutions.mix.title')} action={q.data && <Tag tone="neutral">{t('solutions.count', { n: live.length })}</Tag>}>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(84px, auto) minmax(0,1fr) 32px', gap: 1, alignItems: 'center' }}>
        {codes.map((c) => {
          const n = counts.get(c.code) ?? 0;
          const mine = c.code === current;
          return (
            <Box key={c.code} sx={{ display: 'contents' }}>
              <Typography sx={{ fontSize: 13, fontWeight: mine ? 700 : 400, color: mine ? 'text.primary' : 'text.secondary' }}>{c.label}</Typography>
              <Box sx={(th) => ({ height: 32, borderRadius: '10px', bgcolor: th.vars.palette.background.subtle, overflow: 'hidden',
                outline: mine ? `2px solid ${th.vars.palette.status.caution}` : 'none', outlineOffset: 1 })}>
                <Box sx={(th) => ({ height: '100%', width: `${(n / max) * 100}%`, minWidth: n ? 10 : 0, borderRadius: '10px',
                  bgcolor: mine ? th.vars.palette.brand.ftcViolet : th.vars.palette.brand.purpleTint })} />
              </Box>
              <Typography sx={{ fontFamily: MONO, fontSize: 14, fontWeight: 600, textAlign: 'right',
                color: n ? 'text.primary' : 'text.disabled' }}>{n || '·'}</Typography>
            </Box>
          );
        })}
      </Box>
      <Typography sx={{ fontSize: 12.5, color: 'brand.muted' }}>{t('solutions.mix.note')}</Typography>
    </Card>
  );
}
