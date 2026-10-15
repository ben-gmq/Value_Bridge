import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, FormControlLabel, Stack, Typography } from '@mui/material';
import { dfdRuleApi } from '../../api/scope';
import { errorText } from '../../api/client';
import { keys } from '../../app/links';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, ListRow, Segmented, Tag } from '../../components/kit';
import { t } from '../../i18n/t';

const SETS = ['TO_BE', 'AS_IS'];
const same = (a, b) => a.length === b.length && a.every((x) => b.includes(x));

/**
 * Settings → Components: the project's DFD rule (D-70). Per chart, the elements every process needs before the scope
 * can be frozen. Everyone sees it; only a platform admin changes it, through a preview that says how many processes
 * (and, for an outside party, diagrams) the next freeze would refuse, then a save carrying the preview's digest. Option
 * A (Q-3): "something starts it" is always required, and the order needs both data elements because it is derived from
 * them. The checks follow the server's catalogue; the server validates again (422).
 */
export function DfdRuleCard({ projectId, isAdmin, onNotice }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: keys.dfdRule(projectId), queryFn: () => dfdRuleApi.get(projectId) });
  const [set, setSet] = useState('TO_BE');
  const [wanted, setWanted] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const chart = q.data?.charts.find((c) => c.bfc_set_code === set);
  const catalogue = useMemo(() => q.data?.catalogue ?? [], [q.data]);

  useEffect(() => { if (chart) setWanted(chart.codes); }, [chart]);

  const review = useMutation({
    mutationFn: () => dfdRuleApi.preview(projectId, { bfc_set_code: set, codes: wanted }),
    onSuccess: (res) => { setError(''); setPreview(res); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const save = useMutation({
    mutationFn: () => dfdRuleApi.save(projectId, { bfc_set_code: set, codes: wanted, row_version: q.data.row_version,
      preview_digest: preview.preview_digest }),
    onSuccess: () => {
      setError(''); setPreview(null); onNotice?.(t('components.dfdRule.saved'));
      for (const k of [keys.dfdRule(projectId), keys.tree(projectId), keys.flows(projectId), keys.project(projectId)]) {
        qc.invalidateQueries({ queryKey: k });              // the lights, marks and gaps all follow the rule
      }
    },
    onError: (err) => { setPreview(null); setError(errorText(err, t('common.saveFailed'))); },
  });

  const toggle = (code) => setWanted((w) => {
    if (w.includes(code)) {
      // dropping a data element drops what needs it (ORDER), so the set stays valid
      return w.filter((c) => c !== code && !(catalogue.find((e) => e.code === c)?.requires ?? []).includes(code));
    }
    return catalogue.map((e) => e.code).filter((c) => c === code || w.includes(c));
  });
  const changed = chart && wanted && !same(chart.codes, wanted);

  return (
    <Card title={t('components.dfdRule.title')} bodySx={{ gap: 1.25 }}
      action={<Segmented size="sm" label={t('components.dfdRule.chart')} value={set} onChange={(v) => { setSet(v); setPreview(null); }}
        options={SETS.map((v) => ({ value: v, label: t(`components.dfdRule.set.${v}`) }))} />}>
      <Typography sx={{ color: 'text.secondary', fontSize: 13.5 }}>{t('components.dfdRule.what')}</Typography>
      {q.error && <Alert severity="error">{errorText(q.error)}</Alert>}
      {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
      {chart && !chart.rule_applies && <Alert severity="info">{t('components.dfdRule.off')}</Alert>}
      {chart?.fallback && <Alert severity="warning">{t('components.dfdRule.fallback')}</Alert>}
      {chart && wanted && catalogue.map((e) => {
        const on = wanted.includes(e.code);
        const blockedBy = e.requires.filter((r) => !wanted.includes(r));
        return (
          <ListRow key={e.code} selected={on} sx={{ py: 0.5, flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <FormControlLabel sx={{ mr: 'auto', alignItems: 'flex-start', minWidth: 0, flex: '1 1 220px' }}
              disabled={!isAdmin || e.locked || (!on && blockedBy.length > 0)}
              control={<Checkbox checked={on} onChange={() => toggle(e.code)} sx={{ mt: -0.5 }} />}
              label={(
                <Box sx={{ minWidth: 0 }}>
                  <Typography sx={{ fontSize: 14, fontWeight: 600 }}>{t(`components.dfdRule.element.${e.code}.label`)}</Typography>
                  <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>
                    {t(`components.dfdRule.element.${e.code}.help`)}</Typography>
                </Box>)} />
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', alignSelf: 'center' }}>
              {e.locked && <Tag tone="neutral">{t('components.dfdRule.locked')}</Tag>}
              {chart.recommended.includes(e.code) && <Tag tone="ok">{t('components.dfdRule.recommended')}</Tag>}
              {e.per_diagram && <Tag tone="navy">{t('components.dfdRule.perDiagram')}</Tag>}
            </Box>
          </ListRow>
        );
      })}
      {isAdmin && chart && (
        <Box>
          <Button variant="contained" disabled={!changed || review.isPending} onClick={() => review.mutate()}>
            {t('components.dfdRule.review')}</Button>
        </Box>
      )}
      <ConfirmDialog open={Boolean(preview)} title={t('components.dfdRule.reviewTitle', { chart: t(`components.dfdRule.set.${set}`) })}
        confirmLabel={t('components.dfdRule.apply')} busy={save.isPending}
        body={preview ? t('components.dfdRule.reviewBody', { list: preview.codes.map((c) => t(`components.dfdRule.element.${c}.label`)).join(', ') }) : ''}
        onClose={() => setPreview(null)} onConfirm={() => save.mutate()}>
        {preview && (
          <Stack spacing={1}>
            {!preview.rule_applies && <Alert severity="info">{t('components.dfdRule.off')}</Alert>}
            <Typography>{t('components.dfdRule.counts', { ready: preview.ready, partly: preview.partly, not: preview.not_ready })}</Typography>
            <Alert severity={preview.would_block || preview.would_block_diagrams ? 'warning' : 'success'}>
              {preview.would_block || preview.would_block_diagrams
                ? t('components.dfdRule.wouldBlock', { n: preview.would_block, d: preview.would_block_diagrams })
                : t('components.dfdRule.blocksNone')}
            </Alert>
          </Stack>
        )}
      </ConfirmDialog>
    </Card>
  );
}
